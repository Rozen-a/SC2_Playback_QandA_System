"""
验证 T06 Runnable 五步链的证据交接与失败停止。
"""

from importlib.util import find_spec
from unittest import TestCase, skipUnless
from unittest.mock import Mock

from src.chain import build_chain


@skipUnless(find_spec("langchain_core"), "请先安装 langchain-core")
class ChainTests(TestCase):
    """
使用回放 A 的真实统计与模拟检索、模型响应验证链路。
    """

    def test_mixed_evidence_reaches_one_generation(self):
        """
        核对双方矿量、Tracker 来源和说明片段进入同一次生成。
        """
        note = {"id": "K01", "title": "当前矿量", "text": "玩家当前可用的矿量。",
                "source": {"path": "docs/fields.md", "section": "字段对应"}}
        gas_note = {**note, "id": "K02", "title": "当前气量", "text": "玩家当前可用的气量。"}
        search = Mock(return_value=[note, gas_note])
        text = "双方数值：Lambo 35，MaxPax 40\n字段含义：当前可用矿量\n数值来源：tracker_index=238、239\n说明来源：K01"
        generate = Mock(return_value={"response": {"answer": text}})
        result = build_chain(search, generate).invoke({"question": "回放 A 的第二个采样点，双方当前矿量各是多少？"})
        self.assertEqual(result["status"], "ok")
        self.assertEqual([step["name"] for step in result["steps"]],
                         ["parameters", "query", "retrieval", "assembly", "answer"])
        self.assertEqual(result["game_loop"], 160)
        self.assertEqual([(row["minerals_current"], row["tracker_index"]) for row in result["evidence"]["records"]],
                         [(35, 238), (40, 239)])
        self.assertEqual(result["evidence"]["notes"], [note])
        self.assertEqual(result["notes"], [note, gas_note])
        prompt = result["answer_prompt"]
        labels = ("双方数值：", "字段含义：", "数值来源：", "说明来源：")
        positions = [prompt.rindex(label) for label in labels]
        self.assertEqual(positions, sorted(positions))
        self.assertGreater(positions[0], prompt.rindex('"notes"'))
        generate.assert_called_once_with(result["answer_prompt"])

        # K02 确实被召回，但矿量题没有将它送入模型，引用时应被拒绝。
        invalid = text.replace("说明来源：K01", "说明来源：K01、K02")
        generate.return_value = {"response": {"answer": invalid}}
        failed = build_chain(search, generate).invoke({"question": result["question"]})
        self.assertEqual(failed["error"]["code"], "invalid_sources")
        self.assertEqual(failed["response"]["response"]["answer"], invalid)

        gas_text = "双方数值：Lambo 0，MaxPax 0\n字段含义：当前可用气量\n数值来源：238、239\n说明来源：K02"
        generate.return_value = {"response": {"answer": gas_text}}
        gas = build_chain(search, generate).invoke({"question": "回放 A 的第二个采样点，当前气量是什么意思？"})
        self.assertEqual(gas["status"], "ok")
        self.assertEqual(gas["evidence"]["notes"], [gas_note])

        # 缺少气量定义时仍可返回数值，并明确说明资料不足。
        search.return_value = [note]
        generate.return_value = {"response": {"answer": gas_text.replace(
            "当前可用气量", "当前资料不足").replace("说明来源：K02", "说明来源：无相关资料")}}
        missing = build_chain(search, generate).invoke({"question": gas["question"]})
        self.assertEqual(missing["status"], "ok")
        self.assertEqual(missing["evidence"]["notes"], [])

    def test_invalid_ordinal_stops_downstream_calls(self):
        """
        时刻不可查时保留可选时刻，并跳过检索和生成。
        """
        search, generate = Mock(), Mock()
        result = build_chain(search, generate).invoke({"question": "回放 A 的第999999个采样点，当前矿量是多少？"})
        self.assertEqual(result["error"]["stage"], "query")
        self.assertIn(160, result["error"]["available_game_loops"])
        search.assert_not_called()
        generate.assert_not_called()
