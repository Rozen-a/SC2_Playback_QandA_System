"""检查已导出的六条样本与原始统计材料的对应关系。"""
import csv
import hashlib
import json
import unittest
from pathlib import Path


class ExportRecordTests(unittest.TestCase):
    def test_sample_matches_raw_evidence(self):
        root = Path(__file__).resolve().parents[1]
        raw_path = root / "data/decoded/A_tracker_stats.json"
        if not raw_path.exists():
            self.skipTest("请先运行 src/parse_replay.py 生成导出文件。")
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        with (root / "data/processed/A_stats_sample.csv").open(
            encoding="utf-8-sig", newline=""
        ) as file:
            rows = list(csv.DictReader(file))
        self.assertEqual(len(rows), 6)
        self.assertEqual(len({(r["pid"], r["game_loop"]) for r in rows}), 6)
        source_path = root / "data/raw" / raw["source"]["source_file"]
        self.assertEqual(
            hashlib.sha256(source_path.read_bytes()).hexdigest().upper(),
            raw["source"]["sha256"],
        )
        events = {event["tracker_index"]: event for event in raw["events"]}
        for row in rows:
            event = events[int(row["tracker_index"])]
            self.assertEqual(event["pid"], int(row["pid"]))
            self.assertEqual(event["game_loop"], int(row["game_loop"]))
            self.assertEqual(event["player_name"], row["player_name"])
            # 检查真正保存的是统计值，不是把字典键误导出成数组。
            self.assertIsInstance(event["raw_stats"], dict)
            for field, index in (("minerals_current", "0"),
                                 ("vespene_current", "1"),
                                 ("workers_active_count", "4")):
                check = event["field_checks"][field]
                self.assertEqual(check["raw"], event["raw_stats"].get(index))
                if check["status"] == "raw_matches_parser":
                    self.assertEqual(int(row[field]), event["raw_stats"][index])
                else:
                    self.assertEqual(row[field], "")


if __name__ == "__main__":
    unittest.main()
