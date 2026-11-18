"""
验证 T07 会话隔离和最近消息保留规则。
"""

from unittest import TestCase

from src.context import SessionStore


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
