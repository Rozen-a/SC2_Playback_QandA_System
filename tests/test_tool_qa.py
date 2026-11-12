"""
用模拟模型回答和回放 A 的真实统计表验证 T04 查询问答流程。
"""

from pathlib import Path
import sys
from unittest import TestCase, main
from unittest.mock import Mock

project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.model.model_client import ModelClientError
from src.replay.tool_qa import run_tool_qa


# 模拟模型输出的 JSON 请求和最终回答
STATS_160 = '{"tool":"get_stats","arguments":{"replay_id":"A","game_loop":160}}'
STATS_480 = '{"tool":"get_stats","arguments":{"replay_id":"A","game_loop":480}}'
INFO_A = '{"tool":"get_replay_info","arguments":{"replay_id":"A"}}'


class ToolQATests(TestCase):
    """
核对实际参数、查询证据和失败后的模型调用次数。
    """

    def test_queries_stats_and_passes_signed_difference_to_answer(self):
        """
        查询指定时刻，将真实数值、差值和来源送入回答提示。
        """
        # 模拟模型先返回查询请求，再返回最终回答。
        # 这里的 generate 可以像函数一样调用。`side_effect` 设成列表后，每次调用就取下一个值：
        # 1. 第一次调用 generate(工具请求提示)，返回 STATS_160，模拟模型提出查询请求。
        # 2. 第二次调用 generate(带查询证据的提示)，返回 "Lambo 比 MaxPax 少 5 矿。"，模拟模型给出最终回答。
        # 3. 如果意外调用第三次，列表已经用完，会抛出 StopIteration。
        generate = Mock(side_effect=[STATS_160, "Lambo 比 MaxPax 少 5 矿。"])
        result = run_tool_qa("回放 A 在 game_loop=160 时双方矿量差多少？", generate)
        self.assertEqual(result["status"], "ok")
        # 检查实际调用的工具名、参数和返回结果。这里的 calls 是一个列表，每个元素是一个字典，包含工具名、参数和返回结果。
        # call, = ... 是单元素解包。逗号表示右边必须恰好有一个元素，再把它赋给 call。
        call, = result["tool_calls"]
        self.assertEqual(call["arguments"], {"replay_id": "A", "game_loop": 160})
        # 最后一次调用是回答阶段，检查提示里实际传入的统计证据。
        prompt = generate.call_args.args[0]
        for snippet in ('"minerals_current": 35', '"minerals_current": 40', '"value": -5',
                        '"tracker_index": 238', '"tracker_index": 239'):
            self.assertIn(snippet, prompt)

    def test_resolves_second_sample_from_available_frames(self):
        """
        使用真实可查列表把第二个采样点映射为 160。
        """
        generate = Mock(side_effect=[INFO_A, "第二个采样点是 160。"])
        result = run_tool_qa("回放 A 的第二个采样点双方有多少矿？", generate)
        self.assertEqual(result["status"], "ok")
        self.assertEqual([call["tool"] for call in result["tool_calls"]], ["get_replay_info", "get_stats"])
        self.assertEqual(result["tool_calls"][1]["arguments"]["game_loop"], 160)
        self.assertIn('"sample_ordinal": 2', generate.call_args.args[0])

    def test_retries_wrong_parameter_and_keeps_requested_frame(self):
        """
        模型填错时刻时修正一次，并查询原问题指定的时刻。
        """
        generate = Mock(side_effect=[STATS_480, STATS_160, "少 5 矿。"])
        result = run_tool_qa("回放 A 在 game_loop=160 时差多少矿？", generate)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["attempts"][0]["query_error"]["code"], "wrong_game_loop")
        # 三次模型调用分别是初次请求、一次修正和基于证据的最终回答。
        self.assertEqual(generate.call_count, 3)
        self.assertEqual(len(result["tool_calls"]), 1)

    def test_shares_one_retry_and_stops_without_an_answer(self):
        """
        格式错误与不可查时刻共用一次修正，失败时返回可选时刻。
        """
        unavailable = '{"tool":"get_stats","arguments":{"replay_id":"A","game_loop":999999999}}'
        generate = Mock(side_effect=["{}", unavailable])
        result = run_tool_qa("回放 A 在 game_loop=999999999 时有多少矿？", generate)
        self.assertEqual(result["status"], "query_failed")
        self.assertEqual(result["attempts"][1]["query_error"]["code"], "unavailable_game_loop")
        self.assertIn(160, result["attempts"][1]["query_error"]["available_game_loops"])
        self.assertIsNone(result["answer"])
        # 修正机会已经用完，流程不会再发起回答请求。
        self.assertEqual(generate.call_count, 2)

    def test_preserves_query_when_answer_service_fails(self):
        """
        回答阶段服务超时时，保存已完成的查询和错误。
        """
        generate = Mock(side_effect=[STATS_160, ModelClientError("timeout", "等待超时")])
        result = run_tool_qa("回放 A 在 game_loop=160 时双方矿量差多少？", generate)
        self.assertEqual(result["status"], "model_error")
        self.assertEqual(result["error"]["kind"], "timeout")
        self.assertEqual(result["tool_calls"][0]["arguments"]["game_loop"], 160)


if __name__ == "__main__":
    main(verbosity=2)
