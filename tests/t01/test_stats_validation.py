"""使用固定输入测试 T01 的统计字段校验规则，无需加载回放。"""
import sys
import unittest
from pathlib import Path

# 按文件直接运行时，将仓库根目录加入搜索路径，以支持下面的完整模块路径。
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.replay.stats_validation import check_stat


class StatValidationTests(unittest.TestCase):
    """核对原始统计值正常、缺失、无效或被改写时的校验结果。"""

    def test_zero_is_valid(self):
        """确认真实的零值可以保留在导出结果中。"""
        self.assertEqual(check_stat(0, 0)["value"], 0)

    def test_missing_is_not_zero(self):
        """确认原始值缺失时，解析器给出的零不会填补缺失值。"""
        result = check_stat(None, 0)
        self.assertIsNone(result["value"])
        self.assertEqual(result["status"], "missing")

    def test_negative_clamped_to_zero_is_not_accepted(self):
        """确认负值被解析器改成零时，仍保留原始负值及改写标记。"""
        result = check_stat(-5, 0)
        self.assertIsNone(result["value"])
        self.assertEqual(result["raw"], -5)
        self.assertTrue(result["parser_changed"])

    def test_changed_positive_value_is_not_accepted(self):
        """确认非负整数被解析器改写时，标记不一致并留空。"""
        result = check_stat(50, 51)
        self.assertEqual(result["status"], "parser_mismatch")
        self.assertIsNone(result["value"])

    def test_boolean_is_not_a_count(self):
        """确认布尔值不会因 Python 将 bool 视为 int 的子类而通过校验。"""
        self.assertEqual(check_stat(True, 1)["status"], "invalid_raw")

    def test_string_is_not_silently_converted(self):
        """确认数字字符串不会被自动转换成可导出的整数。"""
        self.assertIsNone(check_stat("12", 12)["value"])


if __name__ == "__main__":
    unittest.main()
