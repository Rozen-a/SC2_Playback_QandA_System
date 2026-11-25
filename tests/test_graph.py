"""
用真实回放查询和模拟模型验证首阶段 StateGraph 节点及终止分支。
"""

from importlib.util import find_spec
from unittest import TestCase, skipUnless
from unittest.mock import Mock

from src.context import SessionStore
from src.graph import build_graph, invoke_session


@skipUnless(find_spec("langgraph"), "请先安装 langgraph")
class GraphTests(TestCase):
    """
    检查完整混合问题和缺少时刻两条执行路径。
    """

    def test_complete_mixed_question(self):
        """
        完整问题执行全部节点，一次生成并保留会话编号与两类证据。
        """
        note = {"id": "K01", "title": "当前矿量", "text": "采样点当前可用的矿量。",
                "source": {"path": "docs/fields.md", "section": "字段对应"}}
        generate = Mock(return_value={"response": {"answer":
            "双方数值：Lambo 35，MaxPax 40\n字段含义：当前可用的矿量\n数值来源：238、239\n说明来源：K01"}})
        graph = build_graph(Mock(return_value=[note]), generate)
        store = SessionStore()
        sid = store.create().session_id
        result = invoke_session(graph, store, sid, "回放 A 的第二个采样点，当前矿量是多少及含义？")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["graph_nodes"], ["parameters", "query", "retrieval", "assembly", "answer", "finish"])
        self.assertEqual(result["session_id"], sid)
        self.assertEqual(result["game_loop"], 160)
        self.assertEqual(result["evidence"]["notes"], [note])
        generate.assert_called_once()

    def test_missing_time_ends_with_clarification(self):
        """
        缺时刻时直接结束，不进入查询、检索或生成。
        """
        search, generate = Mock(), Mock()
        store = SessionStore()
        sid = store.create().session_id
        result = invoke_session(build_graph(search, generate), store, sid, "回放 A 的当前矿量及含义？")
        self.assertEqual(result["status"], "clarify")
        self.assertEqual(result["graph_nodes"], ["parameters", "finish"])
        search.assert_not_called()
        generate.assert_not_called()
