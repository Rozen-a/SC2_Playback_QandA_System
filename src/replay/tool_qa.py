"""
T04 回放问答入口。执行真实查询、调用 T03 回答模板并保存全程记录。
"""

import argparse
from collections.abc import Callable
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

# 按文件直接运行时，Python 从脚本所在目录查找模块。加入仓库根目录以导入 src。
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.model.model_client import PROJECT_ROOT, ModelClientError, request_answer
from src.replay.tool_request import request_tool
from src.tools import ReplayQueryError, get_replay_info, get_stats


# 识别明确的采样点序号、回放编号和 game_loop，用于校验模型是否保留题意。
ORDINAL_PATTERN = re.compile(r"第\s*([0-9]{1,6}|[一二三四五六七八九十])\s*个\s*(?:共同)?(?:采样点|时刻)")
REPLAY_PATTERN = re.compile(r"回放\s*([A-Z])\b", re.ASCII)
FRAME_PATTERN = re.compile(r"\bgame_loop\s*[=＝:]\s*([0-9]{1,9})\b")
ANSWER_PLACEHOLDER = re.compile(r"\{(question|evidence)\}")  # 识别答案模板中的占位符


def build_answer_prompt(question: str, tool_result: dict) -> str:
    """
    用真实查询结果填充 T03 回答模板。

    Args:
        - question (str): 用户原始问题。
        - tool_result (dict): 查询函数返回的回放信息或统计数据。

    Returns:
        - prompt (str): 包含问题和查询证据的回答提示。
    """
    # get_stats()：查询某个采样点，	有 "difference" 键
    # get_replay_info()：查询回放信息，	没有 "difference" 键
    if "difference" in tool_result:
        # 将查询结果整理成 T03 模板使用的 records 和 differences 结构。
        frame = tool_result["game_loop"]
        records = [
            {"game_loop": frame, "player_name": player["player_name"], **player["stats"], **player["source"]}
            for player in tool_result["players"]
        ]
        differences = [
            {
                "field": field,
                "game_loop": frame,
                "minuend_tracker_index": records[0]["tracker_index"],  # 被减数的来源是玩家 1
                "subtrahend_tracker_index": records[1]["tracker_index"],  # 减数的来源是玩家 2
                "value": value,
            }
            for field, value in tool_result["difference"]["values"].items()
        ]
        evidence = {"replay_id": tool_result["replay_id"], "records": records, "differences": differences}
        if "sample_ordinal" in tool_result:
            evidence["sample_ordinal"] = tool_result["sample_ordinal"]
    else:
        # 玩家信息和可选时刻来自元数据，因此来源用回放编号标识。
        evidence = tool_result
        question += "\n来源请写回放信息及回放编号。该查询结果提供的是回放元数据。"
    values = {"question": question, "evidence": json.dumps(evidence, ensure_ascii=False)}
    template = (PROJECT_ROOT / "prompts" / "answer.txt").read_text(encoding="utf-8")
    # 只替换两个占位符，保留模板示例中的 JSON 大括号。
    return ANSWER_PLACEHOLDER.sub(lambda match: values[match[1]], template)


def run_tool_qa(question: str, generate: Callable[[str], str]) -> dict:
    """
    请求工具、校验并查询，再根据查询结果生成回答。

    Args:
        - question (str): 用户的回放查询问题。
        - generate (Callable[[str], str]): 接收提示并返回模型原始回答的函数。

    Returns:
        - result (dict): 状态、请求尝试、实际查询及结果、最终回答或失败原因。
    """
    ordinal_match = ORDINAL_PATTERN.search(question)  # 识别问题中明确的采样点序号
    ordinal = None
    if ordinal_match:
        value = ordinal_match[1]  # 匹配的数字或中文序号
        # 中文序号用字符串的 .index() 方法查找 value 第一次出现的位置，位置从 0 开始计数
        ordinal = int(value) if value.isascii() else "一二三四五六七八九十".index(value) + 1
    replay_match = REPLAY_PATTERN.search(question)  # 识别问题中明确的回放编号
    frame_match = FRAME_PATTERN.search(question)  # 识别问题中明确的 game_loop
    calls = []  # 记录实际调用的工具名、参数和返回结果，供上层检查或调试

    def execute(request: dict) -> dict:
        """
        执行通过格式校验的工具请求，并记录实际调用。

        Args:
            - request (dict): 已校验的工具名与参数。

        Returns:
            - result (dict): 回放信息或最终选中时刻的统计。
        """
        tool = request["tool"]
        arguments = request["arguments"]
        replay_id = arguments["replay_id"]
        # JSON 合法也可能指向另一局或另一时刻。检查问题中能直接识别的限制。
        if replay_match and replay_id != replay_match[1]:
            raise ReplayQueryError("wrong_replay", f"请使用用户指定的回放 {replay_match[1]}。")
        if frame_match and (tool != "get_stats" or arguments["game_loop"] != int(frame_match[1])):
            raise ReplayQueryError("wrong_game_loop", f"请查询用户指定的 game_loop={frame_match[1]}。")
        if ordinal is not None and tool != "get_replay_info":
            raise ReplayQueryError("info_required", "按第几个时刻查询时，请先调用 get_replay_info。")

        # 工具名已通过白名单校验，只分发给两个预先定义的查询函数。
        function = get_replay_info if tool == "get_replay_info" else get_stats
        result = function(**arguments)
        calls.append({"tool": tool, "arguments": arguments, "result": result})
        # 没有明确的采样点序号时，直接返回查询结果
        if ordinal is None:
            return result

        # 从真实可查列表定位序号，使用明确的时刻查询统计。
        frames = result["available_game_loops"]
        if not 1 <= ordinal <= len(frames):
            raise ReplayQueryError("unavailable_ordinal", f"第 {ordinal} 个采样点不可用。", available_game_loops=frames)
        stats_arguments = {"replay_id": replay_id, "game_loop": frames[ordinal - 1]}
        stats = get_stats(**stats_arguments)
        calls.append({"tool": "get_stats", "arguments": stats_arguments, "result": stats})
        return {**stats, "sample_ordinal": ordinal}

    result = request_tool(question, generate, execute)
    result["tool_calls"] = calls
    # 缺少查询结果时，直接返回失败原因，避免调用回答模型猜测数据。
    if result["request"] is None:
        result.update(status="query_failed", answer=None, error=result["attempts"][-1]["error"])
        return result
    try:
        answer = generate(build_answer_prompt(question, result["tool_result"]))
    except ModelClientError as error:
        # 最终生成失败时，保留已经完成的查询、参数和证据供排查。
        result.update(status="model_error", answer=None, error={
            "kind": error.kind, "message": str(error), "http_status": error.status_code, "detail": error.detail,
        })
    else:
        result.update(status="ok", answer=answer)
    return result


def main() -> int:
    """
    读取参数或提示用户输入问题，调用本机模型并保存运行记录。

    Returns:
        - exit_code (int): 查询及回答成功为 0，运行失败或输入结束为 1，用户取消为 130。
    """
    parser = argparse.ArgumentParser(description=__doc__.strip())
    parser.add_argument("--question", help="要查询的回放问题。省略时在终端输入。")
    args = parser.parse_args()
    if args.question is None:
        # 等收到非空问题再读取服务配置，避免因误按回车而发送空请求。
        try:
            question = ""
            while not question:
                question = input("请输入你的回放问题：").strip()
                if not question:
                    print("问题不能为空，请重新输入。")
        except EOFError:
            print("\n未收到问题，已退出。", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("\n已取消输入。", file=sys.stderr)
            return 130
    else:
        question = args.question.strip()
        if not question:
            parser.error("--question 不能为空。")

    config = json.loads((PROJECT_ROOT / "configs" / "model.json").read_text(encoding="utf-8"))
    service = config["service"]
    url = f"http://{service['host']}:{service['port']}"
    expected = {key: config[key] for key in ("model_id", "revision", "enable_thinking", "max_new_tokens")}
    model_calls = []
    record = {"question": question, "service_url": url, "model_calls": model_calls}

    def generate(prompt: str) -> str:
        """
        调用 T02 模型服务并记录实际请求和响应。

        Args:
            - prompt (str): 工具请求、修正请求或回答提示。

        Returns:
            - answer (str): 模型原始输出。
        """
        payload = {"prompt": prompt, "max_new_tokens": expected["max_new_tokens"]}
        entry = {"request": payload}
        # 先保存实际发出的请求，即使服务超时也能看到当时发送的提示。
        model_calls.append(entry)
        result = request_answer(url, payload, service["timeout_seconds"])
        entry.update(result)
        response = result["response"]
        if any(response.get(key) != value for key, value in expected.items()):
            raise ModelClientError("settings_mismatch", "模型服务返回的设置与本地配置不一致。")
        return response["answer"]

    try:
        record.update(run_tool_qa(question, generate))
    except ModelClientError as error:
        record.update(status="model_error", answer=None, error={
            "kind": error.kind, "message": str(error), "http_status": error.status_code, "detail": error.detail,
        })
    except (OSError, ValueError, KeyError) as error:
        record.update(status="input_or_data_error", answer=None, error=str(error))

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = PROJECT_ROOT / "results" / "T04" / f"tool_qa_{run_id}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    # 用独占创建模式保存本次联调记录，防止意外覆盖之前的结果。
    with output.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"运行状态：{record['status']}")
    print(record["answer"] if record["status"] == "ok" else record["error"])
    print(f"运行记录：{output}")
    return 0 if record["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
