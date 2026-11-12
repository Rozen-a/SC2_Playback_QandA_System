"""
用模拟模型输出测试 T04 工具请求协议和修正次数。
"""

from pathlib import Path
import sys
from unittest import TestCase, main
from unittest.mock import Mock

# 按文件直接运行时，从仓库根目录导入 src。
project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.replay.tool_request import parse_tool_request, request_tool


class ToolRequestTests(TestCase):
    """
验证 JSON 请求结构、参数类型和一次修正的边界。
    """

    def test_accepts_both_supported_tools(self):
        """
        接受两个允许的工具及其参数。
        """
        info = '{"tool":"get_replay_info","arguments":{"replay_id":"A"}}'
        stats = '{"tool":"get_stats","arguments":{"replay_id":"A","game_loop":160}}'
        self.assertEqual(parse_tool_request(info), {
            "tool": "get_replay_info", "arguments": {"replay_id": "A"},
        })
        self.assertEqual(parse_tool_request(stats), {
            "tool": "get_stats", "arguments": {"replay_id": "A", "game_loop": 160},
        })

    def test_rejects_invalid_json_and_unknown_tools(self):
        """
        拒绝非 JSON、重复字段、附加内容和未知工具。
        """
        examples = (
            ('非 JSON', "合法 JSON"),
            ('```json\n{}\n```', "合法 JSON"),
            ('{} {}', "合法 JSON"),
            ('{"tool":"get_replay_info","arguments":{"replay_id":"A","replay_id":"B"}}', "不得重复"),
            ('{"tool":"other","arguments":{}}', "工具名"),
        )
        for answer, message in examples:
            with self.subTest(answer=answer), self.assertRaisesRegex(ValueError, message):
                parse_tool_request(answer)

    def test_rejects_wrong_argument_sets_and_types(self):
        """
        拒绝缺少或多余参数、非法回放编号和错误的时刻类型。
        """
        arguments = (
            '{"replay_id":"A"}',
            '{"replay_id":"A","game_loop":160,"extra":0}',
            '{"replay_id":"../A","game_loop":160}',
            '{"replay_id":"A","game_loop":"160"}',
            '{"replay_id":"A","game_loop":160.0}',
            '{"replay_id":"A","game_loop":true}',
            '{"replay_id":"A","game_loop":-1}',
        )
        for value in arguments:
            with self.subTest(arguments=value), self.assertRaises(ValueError):
                parse_tool_request('{"tool":"get_stats","arguments":' + value + '}')

    def test_returns_valid_first_answer_without_retry(self):
        """
        首次校验成功时直接返回并保存原始回答。
        """
        answer = '{"tool":"get_replay_info","arguments":{"replay_id":"A"}}'
        generate = Mock(return_value=answer)
        result = request_tool("回放 A 有哪些时刻？", generate)
        generate.assert_called_once()
        self.assertEqual(result["request"], parse_tool_request(answer))
        self.assertEqual(result["attempts"], [
            {"raw_answer": answer, "request": parse_tool_request(answer), "error": None},
        ])
        self.assertIn('"回放 A 有哪些时刻？"', generate.call_args.args[0])

    def test_retries_once_and_reports_both_attempts(self):
        """
        第二次提示包含错误原因，校验成功时返回修正结果。
        """
        invalid = '{"tool":"get_stats","arguments":{"replay_id":"A","game_loop":"160"}}'
        valid = '{"tool":"get_stats","arguments":{"replay_id":"A","game_loop":160}}'
        # 按顺序模拟首次参数类型错误、第二次修正成功。
        generate = Mock(side_effect=[invalid, valid])
        result = request_tool("查回放 A 在 160 时的统计。", generate)
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(result["request"], parse_tool_request(valid))
        self.assertEqual([attempt["raw_answer"] for attempt in result["attempts"]], [invalid, valid])
        self.assertIn("game_loop 必须是非负 JSON 整数", generate.call_args.args[0])
        self.assertIsNone(result["attempts"][1]["error"])

    def test_stops_after_second_invalid_answer(self):
        """
        两次校验失败后返回失败记录，不继续请求模型。
        """
        generate = Mock(return_value="{}")
        result = request_tool("查回放 A。", generate)
        self.assertEqual(generate.call_count, 2)
        self.assertIsNone(result["request"])
        self.assertEqual(len(result["attempts"]), 2)
        self.assertTrue(all(attempt["error"] for attempt in result["attempts"]))


if __name__ == "__main__":
    main(verbosity=2)
