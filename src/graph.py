"""
T08 首阶段状态图。复用 T06 节点处理完整混合问题与缺条件结束。
"""

from collections.abc import Callable

from src.chain import build_components, session_chain_input
from src.context import SessionStore


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
    为调用方提供按现有会话编号执行单轮完整问题的入口。

    Args:
        graph (CompiledStateGraph): 已编译的状态图。
        store (SessionStore): 会话存储。
        session_id (str): 已存在的会话编号。
        question (str): 本轮完整问题。

    Returns:
        dict: 本轮状态、执行轨迹、原始回答或澄清结果。
    """
    state = session_chain_input(question, store.get(session_id))
    return graph.invoke(state)
