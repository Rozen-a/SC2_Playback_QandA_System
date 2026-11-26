"""
T08 缺条件恢复、会话隔离及取消的回归测试。
"""

import json
from unittest import TestCase
from unittest.mock import Mock

from src.context import SessionStore
from src.graph import build_graph, invoke_session


class GraphSessionTests(TestCase):
    """
    用模拟路由与真实回放查询验证多轮状态。
    """

    def test_missing_condition_resumes_and_clears_pending(self):
        """
        分别验证缺回放和缺时刻，多轮补齐后重新查询。
        """
        for missing in ("replay_id", "sample_ordinal"):
            with self.subTest(missing=missing):
                complete = {"route": "numeric", "replay_id": "A", "sample_ordinal": 2,
                            "game_loop": None, "metric": "minerals_current"}
                partial = {**complete, missing: None}
                router = Mock(side_effect=[{"response": {"answer": json.dumps(r)}} for r in (partial, complete)])
                generate = Mock(return_value={"response": {"answer": "答案：Lambo 35、MaxPax 40。"}})
                search = Mock()
                graph = build_graph(search, generate, router=router)
                store = SessionStore()
                sid = store.create().session_id
                question = ("第二个采样点，当前矿量是多少？" if missing == "replay_id"
                            else "回放 A 当前矿量是多少？")
                first = invoke_session(graph, store, sid, question)
                self.assertEqual(first["status"], "clarify")
                self.assertEqual(first["graph_nodes"], ["route", "finish"])
                self.assertEqual(store.get(sid).pending_question, question)
                generate.assert_not_called()
                other_sid = store.create().session_id
                self.assertIsNone(store.get(other_sid).pending_question)
                second = invoke_session(graph, store, sid,
                                        "回放 A" if missing == "replay_id" else "第二个采样点")
                self.assertEqual(second["status"], "ok")
                self.assertEqual(second["tool_calls"][-1]["arguments"], {"replay_id": "A", "game_loop": 160})
                self.assertIsNone(store.get(sid).pending_question)
                self.assertEqual(store.get(sid).game_loop, 160)
                generate.assert_called_once()
                search.assert_not_called()

    def test_cancel_and_conflicting_supplement_do_not_call_model(self):
        """
        补充与旧问题冲突时保留原问题，明确取消后下一题独立处理。
        """
        store = SessionStore()
        sid = store.create().session_id
        store.set_pending(sid, "回放 A 当前矿量是多少？")
        graph = Mock()
        conflict = invoke_session(graph, store, sid, "回放 B 第二个采样点")
        self.assertEqual(conflict["status"], "clarify")
        self.assertEqual(store.get(sid).pending_question, "回放 A 当前矿量是多少？")
        cancelled = invoke_session(graph, store, sid, "取消旧问题")
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertIsNone(store.get(sid).pending_question)
        graph.invoke.assert_not_called()
        graph.invoke.return_value = {"status": "ok", "question": "当前气量是什么意思？"}
        invoke_session(graph, store, sid, "当前气量是什么意思？")
        self.assertEqual(graph.invoke.call_args.args[0]["question"], "当前气量是什么意思？")
