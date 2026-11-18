"""
T07 本机验收入口。记录真实回放查询和会话变化，并关联已完成的长输入验收。
"""

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from unittest.mock import patch

from src import context


ROOT = Path(__file__).resolve().parents[1]
LONG_INPUT_RUNS = {
    "trim_history": "results/T06/chain_20261118T180009510215Z.json",
    "reject_oversized_question": "results/T06/chain_20261118T180019420529Z.json",
}


def verify_sessions() -> dict:
    """
    交错执行连续追问、换局和新会话验收。

    Returns:
        dict: 实际操作轨迹及逐项检查结果。
    """
    store = context.SessionStore()
    primary = store.create().session_id
    events = []

    # 包装真实查询函数记录调用参数，统计数据仍由原工具读取。
    with (patch.object(context, "get_stats", wraps=context.get_stats) as stats,
          patch.object(context, "get_replay_info", wraps=context.get_replay_info) as info):

        def step(label, session_id, operation):
            """
            执行一个操作并保存会话快照和实际查询参数。

            Args:
                label (str): 操作名称。
                session_id (str): 当前会话编号。
                operation (Callable): 执行该操作的无参数函数。

            Returns:
                dict: 包含操作结果与核对所需证据的记录。
            """
            stats.reset_mock()
            info.reset_mock()
            before = asdict(store.get(session_id))
            result = operation()
            event = {"operation": label, "session_id": session_id,
                     "before": before, "after": asdict(store.get(session_id)), "result": result,
                     "stats_arguments": [list(call.args) for call in stats.call_args_list],
                     "info_arguments": [list(call.args) for call in info.call_args_list]}
            events.append(event)
            return event

        def seed_query(replay_id, player, ordinal):
            """
            从可查列表定位首轮时刻，查数并存入已确认条件。

            Args:
                replay_id (str): 回放编号。
                player (str): 首轮焦点玩家。
                ordinal (int): 从 1 起算的采样点序号。

            Returns:
                dict: 实际时刻、矿量和来源。
            """
            frame = context.get_replay_info(replay_id)["available_game_loops"][ordinal - 1]
            result = context.get_stats(replay_id, frame)
            row = next(row for row in result["players"] if row["player_name"] == player)
            store.update_target(primary, replay_id=replay_id, player_name=player, game_loop=frame,
                                metric="minerals_current")
            return {"game_loop": frame, "player_name": player,
                    "value": row["stats"]["minerals_current"], "source": row["source"]}

        first = step("查 A 的第二个采样点", primary, lambda: seed_query("A", "Lambo", 2))
        gas, other, later = [
            step(question, primary, lambda: context.query_followup(store, primary, question))
            for question in ("同一时刻的气呢？", "另一方呢？", "下一个采样点呢？")
        ]
        switch = step("切换到 B", primary, lambda: asdict(store.switch_replay(primary, "B")))
        unclear = step("换局后追问同一时刻的气", primary,
                       lambda: context.query_followup(store, primary, "同一时刻的气呢？"))
        b = step("明确 B 的第二个采样点", primary, lambda: seed_query("B", "DnS", 2))
        fresh = store.create().session_id
        new = step("新会话追问另一方", fresh, lambda: context.query_followup(store, fresh, "另一方呢？"))
        resumed = step("回到原会话追问气量", primary,
                       lambda: context.query_followup(store, primary, "同一时刻的气呢？"))

    checks = {
        "initial_query": (first["result"]["value"], first["result"]["source"]["tracker_index"]) == (35, 238),
        "followup_queries": [gas["stats_arguments"], other["stats_arguments"], later["stats_arguments"]]
        == [[["A", 160]], [["A", 160]], [["A", 320]]],
        "followup_values_and_sources": [
            (row["player_name"], row["value"], row["source"]["tracker_index"])
            for event in (gas, other, later) for row in event["result"].get("records", [])
        ] == [("Lambo", 0, 238), ("MaxPax", 0, 239), ("MaxPax", 0, 247)],
        "switch_clears_target": switch["after"]["session_id"] == primary and switch["after"]["replay_id"] == "B"
        and all(switch["after"][field] is None for field in ("player_name", "game_loop", "metric"))
        and not switch["after"]["messages"],
        "missing_time_clarifies": unclear["result"]["status"] == "clarify" and not unclear["stats_arguments"],
        "query_uses_b_source": b["stats_arguments"] == [["B", 160]] and b["result"]["value"] == 40
        and b["result"]["source"]["tracker_index"] == 278,
        "new_session_isolated": fresh != primary and new["before"]["replay_id"] is None
        and new["result"]["status"] == "clarify" and not new["stats_arguments"]
        and resumed["before"] == b["after"] and resumed["stats_arguments"] == [["B", 160]]
        and resumed["result"]["status"] == "ok",
    }
    return {"checks": checks, "events": events}


def main() -> int:
    """
    汇总会话验收和已保存的长输入结果。

    Returns:
        int: 全部通过时为 0，否则为 1。
    """
    report = verify_sessions()
    report["long_input"] = {}
    for label, name in LONG_INPUT_RUNS.items():
        run = json.loads((ROOT / name).read_text(encoding="utf-8"))
        audit = run["prompt_budget"]
        report["long_input"][label] = {"path": name, "budget": audit,
                                       "generation_requests": run["generation_requests"], "status": run["status"]}
        if label == "trim_history":
            passed = (run["status"] == "ok" and run["generation_requests"] == 1
                      and audit["removed"] == [{"type": "history", "index": 0}]
                      and audit["kept_history_indices"] == [1]
                      and audit["input_tokens"] == run["response"]["response"]["input_tokens"])
        else:
            passed = (run["generation_requests"] == 0 and not audit["fits"]
                      and run["error"]["code"] == "prompt_too_long")
        report["checks"][label] = passed

    report["status"] = "ok" if all(report["checks"].values()) else "failed"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = ROOT / "results" / "T07" / f"acceptance_{run_id}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"T07 {report['status']}，运行记录：{output}")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
