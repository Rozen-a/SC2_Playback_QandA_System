"""核对 T01 已导出的 CSV 样本、事件 JSON 和原始回放文件。"""
import csv
import hashlib
import json
import unittest
from pathlib import Path


class ExportRecordTests(unittest.TestCase):
    """检查六条样本能否追溯到当前回放的对应统计事件。"""

    def test_sample_matches_raw_evidence(self):
        """核对样本数量、来源校验值、事件身份和各统计字段。"""
        root = Path(__file__).resolve().parents[2]
        raw_path = root / "data/decoded/A_tracker_stats.json"
        # 本用例读取现有导出产物。尚未生成原始事件 JSON 时，提示先运行解析程序。
        if not raw_path.exists():
            self.skipTest("请先运行 src/replay/parse_replay.py 生成导出文件。")
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        with (root / "data/processed/A_stats_sample.csv").open(
            encoding="utf-8-sig", newline=""
        ) as file:
            rows = list(csv.DictReader(file))
        # 三个共同采样时刻各有双方记录。同一玩家和时刻的组合只能出现一次。
        self.assertEqual(len(rows), 6)
        self.assertEqual(len({(r["pid"], r["game_loop"]) for r in rows}), 6)
        # 用当前文件的实际字节重算 SHA-256，核实导出记录中的来源。
        source_path = root / "data/raw" / raw["source"]["source_file"]
        self.assertEqual(
            hashlib.sha256(source_path.read_bytes()).hexdigest().upper(),
            raw["source"]["sha256"],
        )
        # tracker_index 是原始 Tracker 事件序号，用它定位事件，避免依赖 JSON 中的排列位置。
        events = {event["tracker_index"]: event for event in raw["events"]}
        for row in rows:
            event = events[int(row["tracker_index"])]
            self.assertEqual(event["pid"], int(row["pid"]))
            self.assertEqual(event["game_loop"], int(row["game_loop"]))
            self.assertEqual(event["player_name"], row["player_name"])
            # JSON 对象的字段索引是字符串，分别对应当前矿量、气量和活跃工人数。
            self.assertIsInstance(event["raw_stats"], dict)
            for field, index in (("minerals_current", "0"),
                                 ("vespene_current", "1"),
                                 ("workers_active_count", "4")):
                check = event["field_checks"][field]
                self.assertEqual(check["raw"], event["raw_stats"].get(index))
                # 校验通过的数值应与原始统计一致，其余状态在 CSV 中留空。
                if check["status"] == "raw_matches_parser":
                    self.assertEqual(int(row[field]), event["raw_stats"][index])
                else:
                    self.assertEqual(row[field], "")


if __name__ == "__main__":
    unittest.main()
