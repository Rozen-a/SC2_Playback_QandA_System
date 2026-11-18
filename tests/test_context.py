"""
验证 T07 会话隔离和最近消息保留规则。
"""

from unittest import TestCase
from unittest.mock import patch

from src.context import SessionStore, query_followup
from src.tools import ReplayQueryError, get_stats


class SessionStoreTests(TestCase):
    """
测试独立会话编号、状态更新和历史裁剪。
    """

    def test_interleaved_sessions_keep_separate_targets_and_history(self):
        """
        交错更新两个会话后核对各自的条件和消息。
        """
        store = SessionStore()
        a, b = store.create(), store.create()
        self.assertNotEqual(a.session_id, b.session_id)
        store.update_target(a.session_id, replay_id="A", player_name="Lambo", game_loop=160)
        store.update_target(b.session_id, replay_id="B", player_name="DnS", game_loop=320)
        store.append_message(a.session_id, "user", "查询回放 A")
        store.append_message(b.session_id, "user", "查询回放 B")
        store.update_target(a.session_id, replay_id="A", player_name="MaxPax", game_loop=160)

        current_a, current_b = store.get(a.session_id), store.get(b.session_id)
        self.assertEqual((current_a.replay_id, current_a.player_name, current_a.game_loop), ("A", "MaxPax", 160))
        self.assertEqual((current_b.replay_id, current_b.player_name, current_b.game_loop), ("B", "DnS", 320))
        self.assertEqual([m.content for m in current_a.messages], ["查询回放 A"])
        self.assertEqual([m.content for m in current_b.messages], ["查询回放 B"])

    def test_history_keeps_recent_messages_without_changing_old_snapshot(self):
        """
        历史超出上限时裁掉旧消息，已读快照保持原样。
        """
        store = SessionStore(max_messages=2)
        session_id = store.create().session_id
        earlier = store.append_message(session_id, "user", "第一条")
        store.append_message(session_id, "assistant", "第二条")
        latest = store.append_message(session_id, "user", "第三条")
        self.assertEqual([m.content for m in latest.messages], ["第二条", "第三条"])
        self.assertEqual([m.content for m in earlier.messages], ["第一条"])

    def test_followups_query_each_turn_and_update_target(self):
        """
        核对气量、另一方和下一采样点分别执行真实查询。
        """
        store = SessionStore()
        sid = store.create().session_id
        store.update_target(sid, replay_id="A", player_name="Lambo", game_loop=160, metric="minerals_current")
        with patch("src.context.get_stats", wraps=get_stats) as query:
            gas = query_followup(store, sid, "同一时刻的气呢？")
            other = query_followup(store, sid, "另一方呢？")
            later = query_followup(store, sid, "下一个采样点呢？")
        self.assertEqual([(c.args) for c in query.call_args_list], [("A", 160), ("A", 160), ("A", 320)])
        self.assertEqual((gas["metric"], gas["records"][0]["value"]), ("vespene_current", 0))
        self.assertEqual(other["records"][0]["player_name"], "MaxPax")
        self.assertEqual(store.get(sid).game_loop, later["game_loop"])

    def test_other_side_without_focus_needs_clarification(self):
        """
        没有焦点玩家时追问另一方，不执行查询或修改已有状态。
        """
        store = SessionStore()
        sid = store.create().session_id
        before = store.update_target(sid, replay_id="A", player_name=None, game_loop=160, metric="minerals_current")
        with patch("src.context.get_stats") as query:
            self.assertEqual(query_followup(store, sid, "另一方？")["status"], "clarify")
            query.assert_not_called()
        self.assertEqual(store.get(sid), before)

    def test_switch_clears_conditions_without_affecting_other_sessions(self):
        """
        换局清除旧条件，新会话独立，另一个已有会话仍保留原状态。
        """
        store = SessionStore()
        a, b = store.create().session_id, store.create().session_id
        store.update_target(a, replay_id="A", player_name="Lambo", game_loop=160, metric="minerals_current")
        store.append_message(a, "assistant", "Lambo 当前矿量 35")
        other = store.update_target(b, replay_id="A", player_name="MaxPax", game_loop=320)
        switched = store.switch_replay(a, "B")
        fresh = store.create()
        self.assertEqual((switched.session_id, switched.replay_id), (a, "B"))
        self.assertEqual((switched.player_name, switched.game_loop, switched.metric, switched.messages),
                         (None, None, None, ()))
        self.assertNotIn(fresh.session_id, {a, b})
        self.assertIsNone(fresh.replay_id)
        with patch("src.context.get_stats", wraps=get_stats) as query:
            self.assertEqual(query_followup(store, a, "同一时刻的气呢？")["status"], "clarify")
            self.assertEqual(query_followup(store, fresh.session_id, "另一方呢？")["status"], "clarify")
            query.assert_not_called()
            self.assertEqual(store.get(b), other)
            self.assertEqual(query_followup(store, b, "同一时刻的气呢？")["status"], "ok")
            query.assert_called_once_with("A", 320)

    def test_failed_switch_preserves_state(self):
        """
        无效换局和直接改写回放编号均无法污染当前会话。
        """
        store = SessionStore()
        sid = store.create().session_id
        before = store.update_target(sid, replay_id="A", player_name="Lambo", game_loop=160)
        with self.assertRaises(ReplayQueryError):
            store.switch_replay(sid, "../B")
        with self.assertRaises(ValueError):
            store.update_target(sid, replay_id="B", player_name="Lambo", game_loop=160)
        self.assertEqual(store.get(sid), before)
