"""
T08 三类路线节点。校验原始模型的路线参数并复用现有查询与说明接口。
"""

import json
import re
from collections.abc import Callable

from src.chain import METRICS, assemble_answer, query_stats
from src.model.model_client import ModelClientError
from src.rag_qa import build_answer_prompt as explanation_prompt
from src.replay.tool_qa import build_answer_prompt as numeric_prompt, read_explicit_target
from src.replay.tool_request import _unique_object
from src.retrieval import PROJECT_ROOT


def route_parameters(question: str, router: Callable[[str], dict]) -> dict:
    """
    请求原始模型给出路线和参数，检查结构、类型及明确用户条件。

    Args:
        question (str): 当前完整问题。
        router (Callable): 原始模型客户端，返回包含 response.answer 的结果。

    Returns:
        dict: 路由原始记录、合法参数，或结构化错误。
    """
    template = (PROJECT_ROOT / "prompts/route_request.txt").read_text(encoding="utf-8")
    prompt = template.replace("{question}", json.dumps(question, ensure_ascii=False))
    # 先保留实际提示；模型调用失败时，仍能知道本轮发送了什么问题。
    fields = {"route_prompt": prompt}
    try:
        response = router(prompt)
        fields["route_response"] = response
        # 只接收可解析的 JSON；沿用 T04 的钩子拒绝重复键，避免同名参数被静默覆盖。
        request = json.loads(response["response"]["answer"], object_pairs_hook=_unique_object)
        required = {"route", "replay_id", "sample_ordinal", "game_loop", "metric"}
        # 比较键集合而非顺序：五个字段必须齐全，缺失条件应显式写 null。
        if not isinstance(request, dict) or set(request) != required:
            raise ValueError("路线请求字段不完整或包含额外字段。")
        route = request["route"]
        if route not in ("numeric", "explanation", "mixed"):
            raise ValueError("路线只能为 numeric、explanation 或 mixed。")
        replay, ordinal, frame, metric = (request[k] for k in
                                         ("replay_id", "sample_ordinal", "game_loop", "metric"))
        if metric is not None and metric not in METRICS.values():
            raise ValueError("统计指标不在允许列表内。")
        if replay is not None and (not isinstance(replay, str) or not re.fullmatch("[A-Z]", replay)):
            raise ValueError("回放编号格式错误。")
        # 序号从 1 起、帧号从 0 起；type 精确检查也会排除布尔值。
        for name, value, minimum in (("sample_ordinal", ordinal, 1), ("game_loop", frame, 0)):
            if value is not None and (type(value) is not int or value < minimum):
                raise ValueError(f"{name} 类型或范围错误。")
        if ordinal is not None and frame is not None:
            raise ValueError("不能同时指定采样点序号和 game_loop。")
        explicit_replay, explicit_ordinal, explicit_frame = read_explicit_target(question)
        if route != "explanation":
            # 首阶段仅接受当前问题明确提供的时刻和回放，后续接入会话补条件。
            if (replay, ordinal, frame) != (explicit_replay, explicit_ordinal, explicit_frame):
                raise ValueError("模型参数与用户明确提供的回放或时刻不一致。")
            if replay is None or (ordinal is None and frame is None) or metric is None:
                # 仅对合法且如实缺条件的请求逐项提示；非法 JSON 不走此恢复入口。
                missing = []
                if replay is None:
                    missing.append("回放编号")
                if ordinal is None and frame is None:
                    missing.append("采样点序号或 game_loop")
                if metric is None:
                    missing.append("统计指标")
                return {**fields, **request, "status": "clarify", "missing_fields": missing,
                        "message": "请补充：" + "、".join(missing) + "。"}
        elif any(value is not None for value in (replay, ordinal, frame)):
            raise ValueError("解释路线的回放和时刻应为空。")
        # 用原问题中可识别的指标反查模型参数，防止 JSON 合法但查错字段。
        labels = [label for label, field in METRICS.items() if label in question or field in question]
        if labels and (len(labels) != 1 or METRICS[labels[0]] != metric):
            raise ValueError("模型指标与用户问题不一致。")
        return {**fields, **request, "metric_label": next(
            (label for label, field in METRICS.items() if field == metric), question)}
    except (ValueError, KeyError, TypeError, RecursionError, ModelClientError) as error:
        return {**fields, "status": "error", "error": {
            "stage": "route", "code": getattr(error, "kind", "invalid_route"), "message": str(error)}}


def build_routed_graph(search: Callable, generate: Callable, router: Callable, *, budget=None):
    """
    编译三路线图，分别执行查询、检索或两者。

    Args:
        search (Callable): 说明检索函数。
        generate (Callable): 最终回答客户端。
        router (Callable): 固定使用原始模型的路线客户端。
        budget (tuple | None): 实际分词计数、上下文上限、输出预留。

    Returns:
        CompiledStateGraph: 三类问答路线图。
    """
    from langgraph.graph import START, END, StateGraph
    from src.chain import build_components
    from src.prompt_budget import fit_prompt

    shared = build_components(search, generate, budget=budget)

    def retrieval(state: dict) -> dict:
        """
        按说明问题检索，保留候选片段。

        Args:
            state (dict): 问题和路线参数。

        Returns:
            dict: 检索问题和候选片段。
        """
        # 纯解释题保留原问题；混合题只检索指标定义，避免对局编号影响召回。
        query = state["question"] if state["route"] == "explanation" else state["metric_label"] + "是什么意思？"
        return {"retrieval_query": query, "notes": search(query)}

    def assembly(state: dict) -> dict:
        """
        按路线使用已有模板组装证据。

        Args:
            state (dict): 查询结果或检索片段。

        Returns:
            dict: 实际提示和证据。
        """
        # 三条路线各用已有提示函数，保持数值证据与文字说明的来源边界。
        if state["route"] == "mixed":
            return assemble_answer(state)
        if state["route"] == "numeric":
            return {"answer_prompt": numeric_prompt(state["question"], state["tool_result"]),
                    "evidence": {"tool_result": state["tool_result"]}}
        return {"answer_prompt": explanation_prompt(state["question"], state["notes"]),
                "evidence": {"notes": state["notes"]}}

    def answer(state: dict) -> dict:
        """
        复用混合回答校验，其他路线保留各自原始回答。

        Args:
            state (dict): 路线、提示和证据。

        Returns:
            dict: 回答结果或预算失败。
        """
        # 混合题沿用 T06 的四行及来源校验；另外两路此处不做同等来源校验。
        if state["route"] == "mixed":
            output = shared["answer"].invoke(state)
            # 外层 wrap 会记录一次 answer，移除内层轨迹以免重复拼接步骤。
            return {k: v for k, v in output.items() if k != "steps"}
        prompt = state["answer_prompt"]
        fields = {}
        if budget is not None:
            counter, limit, reserve = budget
            # 当前问题与已组装证据都必须保留，只允许移除可选历史。
            prompt, _, audit = fit_prompt(lambda _: prompt, counter, state.get("history", ()), (), limit, reserve)
            fields = {"answer_prompt": prompt, "prompt_budget": audit}
            if not audit["fits"]:
                return {**fields, "status": "error", "error": {
                    "stage": "answer", "code": "prompt_too_long", "message": "必要证据超出预算。"}}
        return {**fields, "response": generate(prompt), "status": "ok"}

    def wrap(name: str, operation: Callable):
        """
        为节点保留输入输出，异常时转成可终止状态。

        Args:
            name (str): 节点名称。
            operation (Callable): 节点业务函数。

        Returns:
            Callable: 状态图节点。
        """
        def run(state: dict) -> dict:
            """
            执行并记录当前节点。

            Args:
                state (dict): 当前图状态。

            Returns:
                dict: 合并后的状态及轨迹。
            """
            try:
                fields = operation(state)
            except (OSError, ValueError, KeyError, RuntimeError) as error:
                fields = {"status": "error", "error": {"stage": name,
                          "code": getattr(error, "code", getattr(error, "kind", type(error).__name__)),
                          "message": str(error)}}
            # 用本步输出覆盖同名旧字段，同时追加输入输出快照，方便核对实际路径。
            return {**state, **fields, "steps": [*state.get("steps", []), {
                "name": name, "input": {k: v for k, v in state.items() if k != "steps"}, "output": fields}]}
        return run

    def next_node(state: dict) -> str:
        """
        依据路线和最近执行步骤选择下一节点。

        Args:
            state (dict): 节点执行后的状态。

        Returns:
            str: 下一节点名称。
        """
        # 先检查终止状态，避免错误后仍访问缺失参数或继续调用外部能力。
        if state.get("status") in ("clarify", "error"):
            return "finish"
        last = state["steps"][-1]["name"]
        # 数值题：query→assembly；解释题：retrieval→assembly；
        # 混合题：query→retrieval→assembly。之后都进入 answer 和 finish。
        if last == "route":
            return "retrieval" if state["route"] == "explanation" else "query"
        if last == "query":
            return "retrieval" if state["route"] == "mixed" else "assembly"
        return {"retrieval": "assembly", "assembly": "answer", "answer": "finish"}[last]

    def finish(state: dict) -> dict:
        """
        保存实际执行节点后结束本轮。

        Args:
            state (dict): 本轮最终状态。

        Returns:
            dict: 含图路径的运行记录。
        """
        return {**state, "graph_nodes": [step["name"] for step in state["steps"]] + ["finish"]}

    # START/END 是框架的入口和结束标记，不是额外业务调用。
    graph = StateGraph(dict)
    operations = {"route": lambda state: route_parameters(state["question"], router),
                  "query": query_stats, "retrieval": retrieval, "assembly": assembly, "answer": answer}
    for name, operation in operations.items():
        graph.add_node(name, wrap(name, operation))
    graph.add_node("finish", finish)
    graph.add_edge(START, "route")
    for name in operations:
        graph.add_conditional_edges(name, next_node,
                                    {target: target for target in (*operations, "finish")})
    graph.add_edge("finish", END)
    # compile 构造可执行图；直到调用 invoke 才真正选路、查数、检索和生成。
    return graph.compile()
