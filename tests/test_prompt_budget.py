"""验证 T07 长度预算的保留、裁剪和拒绝规则。"""

from unittest import TestCase

from src.prompt_budget import fit_prompt


class PromptBudgetTests(TestCase):
    """用确定的计数器验证预算策略，无需启动模型服务。"""

    def test_keeps_history_when_budget_allows(self):
        """正常输入保留历史，并为输出预留空间。"""
        prompt, _, audit = fit_prompt(lambda _: "必要证据", len, ["上一轮"], (), 100, 10)
        self.assertIn("上一轮", prompt)
        self.assertTrue(audit["fits"])
        self.assertEqual(audit["kept_history_indices"], [0])

    def test_removes_history_before_optional_notes(self):
        """超限时先丢历史，仍超限才丢无关资料。"""
        prompt, notes, audit = fit_prompt(
            lambda notes: "证据" + "".join(note["id"] for note in notes),
            len, ["上一轮"], [{"id": "K02"}], 4, 2,
        )
        self.assertEqual((prompt, notes), ("证据", []))
        self.assertTrue(audit["fits"])
        self.assertEqual(audit["removed"], [{"type": "history", "index": 0}, {"type": "note", "id": "K02"}])

    def test_rejects_oversized_required_evidence(self):
        """必要证据超限时保留原文，返回拒绝标记。"""
        for text, limit in (("必要证据", 4), ("证" * 4001, 5000)):
            with self.subTest(limit=limit):
                prompt, _, audit = fit_prompt(lambda _: text, len, (), (), limit, 1)
                self.assertEqual(prompt, text)
                self.assertFalse(audit["fits"])
