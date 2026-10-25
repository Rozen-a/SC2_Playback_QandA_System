"""覆盖真实回放未必包含的缺失、异常和改写情况。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from stats_validation import check_stat


class StatValidationTests(unittest.TestCase):
    def test_zero_is_valid(self):
        self.assertEqual(check_stat(0, 0)["value"], 0)

    def test_missing_is_not_zero(self):
        result = check_stat(None, 0)
        self.assertIsNone(result["value"])
        self.assertEqual(result["status"], "missing")

    def test_negative_clamped_to_zero_is_not_accepted(self):
        result = check_stat(-5, 0)
        self.assertIsNone(result["value"])
        self.assertEqual(result["raw"], -5)
        self.assertTrue(result["parser_changed"])

    def test_changed_positive_value_is_not_accepted(self):
        result = check_stat(50, 51)
        self.assertEqual(result["status"], "parser_mismatch")
        self.assertIsNone(result["value"])

    def test_boolean_is_not_a_count(self):
        self.assertEqual(check_stat(True, 1)["status"], "invalid_raw")

    def test_string_is_not_silently_converted(self):
        self.assertIsNone(check_stat("12", 12)["value"])


if __name__ == "__main__":
    unittest.main()
