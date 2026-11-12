"""
T04 工具请求协议。构造模型提示、校验 JSON，并允许修正一次。
"""

from collections.abc import Callable
import json
from pathlib import Path
import re

from src.tools import ReplayQueryError


PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "tool_request.txt"
# 每个允许调用的工具对应一组必填参数。通过集合比较同时检查缺少和多余字段。
TOOL_ARGUMENTS = {
    "get_replay_info": {"replay_id"},
    "get_stats": {"replay_id", "game_loop"},
}


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    """
    构造 JSON 对象，遇到重复字段时报错。

    Args:
        - pairs (list[tuple[str, object]]): JSON 对象中的键和值，按原始顺序排列。

    Returns:
        - result (dict): 键唯一的 JSON 对象。
    """
    # 普通 JSON 解码会保留重复键的最后一个值，这里借助原始键值对识别这种歧义。
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("JSON 对象中的字段不得重复。")
    return result


def parse_tool_request(raw_answer: str) -> dict:
    """
    校验模型生成的工具名、JSON 结构和参数格式。

    Args:
        - raw_answer (str): 模型原始回答，应为单个 JSON 对象。

    Returns:
        - request (dict): 校验通过的工具名和参数。
    """
    try:
        request = json.loads(raw_answer, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, RecursionError) as error:
        raise ValueError("只接受单个合法 JSON 对象。") from error
    # `set(request)` 取得的是字典 request 的键集合，不会取参数值
    if not isinstance(request, dict) or set(request) != {"tool", "arguments"}:
        raise ValueError("请求必须包含且仅包含 tool 和 arguments。")

    tool = request["tool"]
    if not isinstance(tool, str) or tool not in TOOL_ARGUMENTS:
        raise ValueError("工具名必须是 get_replay_info 或 get_stats。")
    arguments = request["arguments"]
    if not isinstance(arguments, dict) or set(arguments) != TOOL_ARGUMENTS[tool]:
        required = "、".join(sorted(TOOL_ARGUMENTS[tool]))  # 先把要求的参数名按字典序排列，再用顿号把它们拼接起来。
        raise ValueError(f"{tool} 的 arguments 必须包含且仅包含 {required}。")

    # 这里只检查参数格式。回放是否存在、时刻是否有数据由查询函数判断。
    replay_id = arguments["replay_id"]
    if not isinstance(replay_id, str) or re.fullmatch(r"[A-Z]", replay_id) is None:
        raise ValueError("replay_id 必须是单个大写英文字母。")
    if tool == "get_stats":
        game_loop = arguments["game_loop"]
        if type(game_loop) is not int or game_loop < 0:
            raise ValueError("game_loop 必须是非负 JSON 整数。")
    return request


def request_tool(
    question: str, generate: Callable[[str], str], execute: Callable[[dict], dict] | None = None
) -> dict:
    """
    请求模型生成工具调用，校验或查询参数错误时共允许一次修正。

    Args:
        - question (str): 用户的回放查询问题。
        - generate (Callable[[str], str]): 接收提示并返回模型原始回答的函数。
        - execute (Callable[[dict], dict] | None): 可选的工具执行函数，接收通过格式校验的请求。

    Returns:
        - result (dict): request 为成功请求或 None，attempts 保存原始回答与错误。
          提供 execute 时，成功结果还包含 tool_result。
    """
    if not question.strip():
        raise ValueError("问题不能为空。")
    template = PROMPT_PATH.read_text(encoding="utf-8")
    # 把问题编码为 JSON 字符串，保留中文，并正确转义其中的引号和换行。
    initial_prompt = template.replace("{question}", json.dumps(question, ensure_ascii=False))
    prompt = initial_prompt
    attempts = []  # 记录原始回答、解析结果和错误信息，供调用方调试或提示用户。

    # 首次请求与一次修正共用同一个循环，JSON 格式和查询参数错误共享修正次数。
    for _ in range(2):
        raw_answer = generate(prompt)
        request = None  # 记录解析出的请求，供上层在捕获 ValueError 时判断是否来自执行阶段。
        query_error = None  # 记录 ReplayQueryError，供上层在捕获 ValueError 时判断是否来自执行阶段。
        try:
            request = parse_tool_request(raw_answer)
            if execute is not None:  # 提供了工具执行函数时，尝试执行查询。
                tool_result = execute(request)
        except ReplayQueryError as error:
            message = str(error)
            query_error = {"code": error.code, "available_game_loops": error.available_game_loops}
            if error.available_game_loops is not None:
                message += f" 可选时刻：{error.available_game_loops}。"
        except ValueError as error:
            # 已解析出合法请求时，普通 ValueError 来自执行阶段，应由上层记录为数据错误。
            if request is not None:
                raise
            message = str(error)
        else:  # 成功时：记录本轮结果，立即返回
            attempts.append({"raw_answer": raw_answer, "request": request, "error": None})
            result = {"request": request, "attempts": attempts}
            if execute is not None:
                result["tool_result"] = tool_result
            return result

        # 解析或执行失败时：记录本轮结果，生成修正提示，继续循环
        attempt = {"raw_answer": raw_answer, "request": request, "error": message}
        if query_error is not None:
            attempt["query_error"] = query_error
        attempts.append(attempt)
        # 数据不一致或指定序号不存在时，重新生成参数无法满足原问题。
        if query_error is not None and query_error["code"] in {"invalid_data", "unavailable_ordinal"}:
            break
        prompt = (
            f"{initial_prompt}\n上一次工具请求失败：{message}\n"
            "请修正工具名或参数，并保持用户指定的回放与时刻。只输出 JSON。"
        )

    return {"request": None, "attempts": attempts}
