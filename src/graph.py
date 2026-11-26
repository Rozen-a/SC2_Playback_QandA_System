"""
T08 首阶段状态图。复用 T06 节点处理完整混合问题与缺条件结束。
"""

from collections.abc import Callable

from src.chain import build_components, session_chain_input
from src.context import SessionStore
from dataclasses import asdict
from src.replay.tool_qa import read_explicit_target


def build_graph(search: Callable, generate: Callable, *, budget=None, router=None):
    """
    编译混合问题状态图，发生错误时通过结束节点返回结果。

    Args:
        search (Callable): 真实或模拟的检索函数。
        generate (Callable): 真实或模拟的生成函数。
        budget (tuple | None): 分词计数函数、上下文上限和输出预留。
        router (Callable | None): 原始模型的路线客户端，提供时启用三路线。

    Returns:
        CompiledStateGraph: 接收字典状态的可执行图。
    """
    # 显式提供路由模型时启用 T08-02；未提供时保持 T08-01 的固定混合路径。
    if router is not None:
        from src.routing import build_routed_graph
        return build_routed_graph(search, generate, router, budget=budget)
    from langgraph.graph import END, START, StateGraph

    components = build_components(search, generate, budget=budget)
    graph = StateGraph(dict)
    for name, node in components.items():
        graph.add_node(name, node)

    def next_node(state: dict) -> str:
        """
        根据执行结果选择结束或继续。

        Args:
            state (dict): 上一个 Runnable 输出的完整状态。

        Returns:
            str: 条件边的分支标识。
        """
        return "stop" if "error" in state else "continue"

    def finish(state: dict) -> dict:
        """
        将缺条件错误整理为澄清提示，记录终止状态。
        澄清提示：信息还不够明确，程序先请用户补充，而不是猜一个条件继续查询。

        Args:
            state (dict): 最后执行步骤返回的状态。

        Returns:
            dict: 包含图节点轨迹及终止结果的状态。
        """
        result = dict(state)
        if state.get("error", {}).get("code") == "invalid_target":
            result.update(status="clarify", message=state["error"]["message"])
        result["graph_nodes"] = [step["name"] for step in state.get("steps", [])] + ["finish"]
        return result

    graph.add_node("finish", finish)
    graph.add_edge(START, "parameters")
    names = list(components)
    # zip(names, names[1:]) 将相邻节点配成对：`parameters → query`、`query → retrieval`，依次到 assembly → answer
    # 每对之间都加一条条件边：
    # - 返回 "continue"：进入下一业务节点。
    # - 返回 "stop"：直接去 finish，后续业务节点不执行。
    for current, following in zip(names, names[1:]):
        graph.add_conditional_edges(current, next_node, {"stop": "finish", "continue": following})
    graph.add_edge("answer", "finish")
    graph.add_edge("finish", END)
    return graph.compile()


def invoke_session(graph, store: SessionStore, session_id: str, question: str) -> dict:
    """
    在同一会话内保存缺条件问题，合并补充后重新进入图。

    Args:
        graph (CompiledStateGraph): 已编译的状态图。
        store (SessionStore): 会话存储。
        session_id (str): 已存在的会话编号。
        question (str): 本轮新问题、对待处理问题的补充，或明确的取消指令。

    Returns:
        dict: 本轮状态、执行轨迹、原始回答或澄清结果。
    """
    question = question.strip()
    if not question:
        raise ValueError("问题不能为空。")
    # 不可变快照既用于读取上一轮条件，也用于记录本轮执行前的会话状态。
    before = store.get(session_id)
    # 取消是明确的会话操作，无需调用模型。只清理待处理问题。
    if question in {"取消", "取消旧问题", "取消当前问题"}:
        after = store.set_pending(session_id, None)
        return {"status": "cancelled", "message": "已取消待处理问题。", "question": question,
                "session_id": session_id, "graph_nodes": [], "session_before": asdict(before),
                "session_after": asdict(after)}
    effective = question
    if before.pending_question is not None:
        # 两次解析均返回 (回放编号, 采样序号, game_loop)，未明确项为 None。
        previous = read_explicit_target(before.pending_question)
        supplement = read_explicit_target(question)
        # 已有回放或时刻与补充冲突时先澄清，避免解析器只选到文本中第一项。
        # 切片只比较两种时间表示；补充未提时间不会触发冲突。
        # 序号与帧号即使可能指向同一时刻，也不会在此猜测其等价关系。
        old_time, new_time = previous[1:], supplement[1:]
        replay_conflict = previous[0] and supplement[0] and previous[0] != supplement[0]
        time_conflict = any(v is not None for v in old_time) and any(v is not None for v in new_time) and old_time != new_time
        if replay_conflict or time_conflict:
            return {"status": "clarify", "message": "补充条件与待处理问题冲突，请取消旧问题后重新提问。",
                    "question": question, "session_id": session_id, "graph_nodes": [],
                    "session_before": asdict(before), "session_after": asdict(before)}
        # 合并文字后重新选路、解析与校验，而非直接信任用户补充并改工具参数。
        # 多次澄清时 effective 会继续保存此前已收到的补充。
        effective = before.pending_question + "\n用户补充：" + question
    state = session_chain_input(effective, before)
    result = graph.invoke(state)
    # 每次图调用从全新单轮状态开始，旧工具结果与错误不会跨轮继承。
    # 只有澄清状态保留待处理意图；ok 和 error 都会清空，并非所有失败都可续接。
    if result.get("status") == "clarify":
        store.set_pending(session_id, effective)
    else:
        store.set_pending(session_id, None)
    # 只在整轮成功且含统计结果时确认目标；纯解释题不覆盖已有数值查询条件。
    if result.get("status") == "ok" and result.get("tool_result"):
        target = result["tool_result"]
        if store.get(session_id).replay_id not in (None, target["replay_id"]):
            store.switch_replay(session_id, target["replay_id"])
        # 图查询双方统计，没有确认单一焦点玩家，故 player_name 明确置空。
        store.update_target(session_id, replay_id=target["replay_id"], player_name=None,
                            game_loop=target["game_loop"], metric=result.get("metric"))
    # 历史保存用户本轮原始输入，合并后的问题保留在图状态中，避免冒充原话。
    # 取消和冲突分支在此前已返回，不会追加这两条历史消息。
    store.append_message(session_id, "user", question)
    answer = result.get("response", {}).get("response", {}).get("answer")
    store.append_message(session_id, "assistant", answer or result.get("message") or
                         result.get("error", {}).get("message", "本轮结束。"))
    return {**result, "user_input": question, "session_before": asdict(before),
            "session_after": asdict(store.get(session_id))}
