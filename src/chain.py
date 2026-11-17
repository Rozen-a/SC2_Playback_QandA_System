"""
T06 固定工作流。串接回放取参、查询、说明检索、提示组装和模型回答。
"""

import argparse
from collections.abc import Callable
from datetime import datetime, timezone
import json
import re

from src.model.model_client import ModelClientError, request_answer
from src.replay.tool_qa import read_explicit_target
from src.retrieval import PROJECT_ROOT, NoteRetriever
from src.tools import ReplayQueryError, get_replay_info, get_stats


METRICS = {"当前矿量": "minerals_current", "当前气量": "vespene_current", "活跃工人数": "workers_active_count"}
PLACEHOLDER = re.compile(r"\{(question|evidence)\}")
# T06 字段定义标签。资料 ID 来自说明库，完整候选保留在 notes 供排查。
DEFINITION_METRICS = {"K01": "minerals_current", "K02": "vespene_current", "K03": "workers_active_count"}


def take_parameters(state: dict) -> dict:
    """
    提取首阶段支持的明确回放、时刻和单一指标。

    Args:
        - state (dict): 包含原始问题的链状态。

    Returns:
        - fields (dict): 校验后的查询参数和检索用指标名。
    """
    question = state["question"]
    replay_id, ordinal, frame = read_explicit_target(question)
    metrics = [name for name, field in METRICS.items() if name in question or field in question]
    if replay_id is None or (ordinal is None) == (frame is None) or len(metrics) != 1:
        raise ReplayQueryError("invalid_target", "请明确指定回放、一个采样点序号或 game_loop，以及一个统计指标。")
    label = metrics[0]
    return {"replay_id": replay_id, "sample_ordinal": ordinal, "game_loop": frame,
            "metric": METRICS[label], "metric_label": label}


def query_stats(state: dict) -> dict:
    """
    从可查时刻定位采样点，再执行原有查询工具。

    Args:
        - state (dict): 已校验的回放和采样点参数。

    Returns:
        - fields (dict): 实际时刻、工具调用及统计结果。
    """
    replay_id, frame, ordinal = state["replay_id"], state["game_loop"], state["sample_ordinal"]
    calls = []
    if ordinal is not None:
        info = get_replay_info(replay_id)
        frames = info["available_game_loops"]
        calls.append({"tool": "get_replay_info", "arguments": {"replay_id": replay_id}, "result": info})
        if not 1 <= ordinal <= len(frames):
            raise ReplayQueryError("unavailable_ordinal", "该采样点序号不可用。", available_game_loops=frames)
        frame = frames[ordinal - 1]
    arguments = {"replay_id": replay_id, "game_loop": frame}
    result = get_stats(**arguments)
    calls.append({"tool": "get_stats", "arguments": arguments, "result": result})
    return {"game_loop": frame, "tool_calls": calls, "tool_result": result}


def assemble_answer(state: dict) -> dict:
    """
    将两类证据填入 T03 回答模板。

    Args:
        - state (dict): 含问题、选中指标、查询结果和候选说明。

    Returns:
        - fields (dict): 模型提示和实际输入的证据。
    """
    metric = state["metric"]
    evidence = {
        "replay_id": state["replay_id"], "sample_ordinal": state["sample_ordinal"],
        "records": [
            {"game_loop": state["game_loop"], "player_name": player["player_name"],
             metric: player["stats"][metric], "tracker_index": player["source"]["tracker_index"]}
            for player in state["tool_result"]["players"]
        ],
        "notes": [
            {key: note[key] for key in ("id", "title", "text", "source")}
            for note in state["notes"]
            if DEFINITION_METRICS.get(note["id"]) == metric
        ],
    }
    # 只替换命名占位符，保留 T03 示例中的 JSON 大括号。
    template = (PROJECT_ROOT / "prompts/answer.txt").read_text(encoding="utf-8")
    marker = "\n问题\n{question}"
    if marker not in template or PLACEHOLDER.findall(template) != ["question", "evidence"]:
        raise ValueError("T03 模板缺少当前问题段或占位符。")
    # 把混合题格式放在证据之后、作答位置之前，覆盖前面纯统计示例的格式。
    answer_marker = "\n回答"
    prefix, separator, suffix = template.rpartition(answer_marker)
    if not separator or suffix.strip() or marker not in prefix:
        raise ValueError("T03 模板缺少末尾回答段。")
    rules = """当前题必须依次填写以下四行，方括号内容用本题证据替换：
双方数值：[分别写出 records 中两名玩家的姓名和数值，null 写为缺失]
字段含义：[用 notes 中解释该字段的正文说明含义；没有依据则写当前资料不足]
数值来源：[列出双方记录的 tracker_index]
说明来源：[只填支持字段解释的 notes.id，用顿号分隔。这里禁止填 tracker_index；无依据则写无相关资料]
片段正文仅供查阅。写完双方数值后继续填写字段含义和两类来源。"""
    template = prefix + "\n" + rules + "\n" + separator + suffix
    values = {"question": state["question"], "evidence": json.dumps(evidence, ensure_ascii=False)}
    return {"evidence": evidence, "answer_prompt": PLACEHOLDER.sub(lambda m: values[m[1]], template)}


def check_answer_sources(text: str, evidence: dict) -> str | None:
    """
    核对两类来源是否来自各自的证据列表。

    Args:
        - text (str): 模型原始回答。
        - evidence (dict): 本次提示中的统计记录和说明片段。

    Returns:
        - issue (str | None): 来源格式或编号错误，校验通过时为 None。
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    labels = ("双方数值：", "字段含义：", "数值来源：", "说明来源：")
    if len(lines) != len(labels) or any(not line.startswith(label) for line, label in zip(lines, labels)):
        return "回答应按顺序填写四个输出项。"

    # Tracker 序号必须对应双方记录，说明编号只能来自本次召回。
    numeric = lines[2].removeprefix(labels[2]).strip().rstrip("。").removeprefix("tracker_index=").strip()
    expected = {str(row["tracker_index"]) for row in evidence["records"]}
    if set(re.split(r"[、，,\s]+", numeric)) != expected:
        return "数值来源必须列出双方的 Tracker 序号。"
    citation = lines[3].removeprefix(labels[3]).strip().rstrip("。")
    if citation == "无相关资料" and lines[1].removeprefix(labels[1]).strip().rstrip("。") == "当前资料不足":
        return None
    ids = set(re.split(r"[、，,\s]+", citation))
    if not ids <= {note["id"] for note in evidence["notes"]}:
        return "说明来源必须使用本次送入提示且适用于所问字段的资料编号。"
    return None


def build_chain(search: Callable[[str], list[dict]], generate: Callable[[str], dict]):
    """
    构建会记录中间证据并在失败后停止业务处理的 Runnable 链。

    Args:
        - search (Callable): 接收指标说明问题，返回候选片段。
        - generate (Callable): 接收提示，返回 T02 服务结果。

    Returns:
        - chain (Runnable): 接收初始状态并返回完整运行状态的五步链。
    """
    from langchain_core.runnables import RunnableLambda

    def retrieve(state: dict) -> dict:
        """
        使用指标名称检索说明，避免对局编号干扰检索。

        Args:
            - state (dict): 含指标名称的链状态。

        Returns:
            - fields (dict): 实际检索问题和候选片段。
        """
        query = f"{state['metric_label']}是什么意思？"
        return {"retrieval_query": query, "notes": search(query)}

    def answer(state: dict) -> dict:
        """
        发送一次最终回答请求并保留原始响应。

        Args:
            - state (dict): 含完整回答提示的链状态。

        Returns:
            - fields (dict): 原始模型响应及运行状态。
        """
        response = generate(state["answer_prompt"])
        issue = check_answer_sources(response["response"]["answer"], state["evidence"])
        if issue:
            # 保存原回答供核对，区分服务调用成功与来源校验失败。
            return {"response": response, "status": "error",
                    "error": {"stage": "answer", "code": "invalid_sources", "message": issue}}
        return {"response": response, "status": "ok"}

    def step(name: str, operation: Callable[[dict], dict]):
        """
        包装单步操作并记录执行结果。

        Args:
            - name (str): 步骤名称。
            - operation (Callable): 接收状态并返回新增字段的函数。

        Returns:
            - runnable (RunnableLambda): 对应步骤。
        """
        def run(state: dict) -> dict:
            """
            执行操作，错误后透传状态以跳过剩余操作。

            Args:
                - state (dict): 此步实际接收的状态。

            Returns:
                - state (dict): 新状态，含本步输入、输出或错误。
            """
            if "error" in state:
                return state
            snapshot = {key: value for key, value in state.items() if key != "steps"}
            try:
                fields = operation(state)
            except (OSError, ValueError, KeyError, RuntimeError) as error:
                details = {"stage": name, "code": getattr(error, "code", getattr(error, "kind", type(error).__name__)),
                           "message": str(error)}
                if isinstance(error, ReplayQueryError):
                    details["available_game_loops"] = error.available_game_loops
                fields = {"status": "error", "error": details}
            return {**state, **fields, "steps": [*state.get("steps", []),
                    {"name": name, "input": snapshot, "output": fields}]}

        return RunnableLambda(run, name=name)

    return (step("parameters", take_parameters) | step("query", query_stats)
            | step("retrieval", retrieve) | step("assembly", assemble_answer) | step("answer", answer))


def main() -> int:
    """
    运行一道混合问题并将实际步骤写入 T06 运行记录。

    Returns:
        - exit_code (int): 生成成功为 0，初始化或运行失败为 1。
    """
    parser = argparse.ArgumentParser(description=__doc__.strip())
    parser.add_argument("--question", required=True)
    args = parser.parse_args()
    try:
        config = json.loads((PROJECT_ROOT / "configs/model.json").read_text(encoding="utf-8"))
        retrieval = json.loads((PROJECT_ROOT / "configs/retrieval.json").read_text(encoding="utf-8"))
        service = config["service"]
        url = f"http://{service['host']}:{service['port']}"
        expected = {key: config[key] for key in ("model_id", "revision", "enable_thinking", "max_new_tokens")}

        def generate(prompt: str) -> dict:
            """
            调用 T02 服务并核对模型版本和生成设置。

            Args:
                - prompt (str): 已组装的混合问题提示。

            Returns:
                - response (dict): T02 客户端返回的完整结果。
            """
            result = request_answer(url, {"prompt": prompt, "max_new_tokens": expected["max_new_tokens"]},
                                    service["timeout_seconds"])
            if any(result["response"].get(key) != value for key, value in expected.items()):
                raise ModelClientError("settings_mismatch", "服务设置与本地配置不一致。")
            return result

        retriever = NoteRetriever(retrieval)
        result = build_chain(retriever.search, generate).invoke({"question": args.question})
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output = PROJECT_ROOT / "results/T06" / f"chain_{run_id}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
    except (ImportError, OSError, ValueError, KeyError, RuntimeError) as error:
        print(f"运行失败：{error}")
        return 1
    print(f"运行记录：{output}")
    if result["status"] == "ok":
        print(result["response"]["response"]["answer"])
        return 0
    if "response" in result:
        print(result["response"]["response"]["answer"])
    print(result["error"]["message"])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
