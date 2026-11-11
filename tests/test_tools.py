"""
直接测试 T04 查询工具的返回值与异常，不调用模型服务。
"""

from pathlib import Path
import sys
from unittest import TestCase, main
from unittest.mock import patch

# IDE 按文件运行时，加入仓库根目录以导入 src。
project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src import tools


class ReplayQueryTests(TestCase):
    """
使用回放 A 的导出数据覆盖正常查询及数据边界。
    """

    def test_lists_only_exported_common_frames(self):
        """
        检查真实玩家名、排序和当前已导出的共同采样点。
        """
        result = tools.get_replay_info("A")
        self.assertEqual([p["name"] for p in result["players"]], ["Lambo", "MaxPax"])
        stats_path = tools.PROCESSED_DIR / "A_stats_sample.csv"
        with stats_path.open(encoding="utf-8-sig", newline="") as stream:
            exported = sorted({int(row["game_loop"]) for row in tools.csv.DictReader(stream)})
        self.assertEqual(result["available_game_loops"], exported)

    def test_returns_stats_source_and_signed_differences(self):
        """
        检查双方数值、来源和差值的负数、正数及零值。
        """
        result = tools.get_stats("A", 160)
        first, second = result["players"]
        self.assertEqual(first["stats"], {
            "minerals_current": 35, "vespene_current": 0, "workers_active_count": 12,
        })
        self.assertEqual(second["stats"]["minerals_current"], 40)
        self.assertEqual(first["source"]["tracker_index"], 238)
        self.assertEqual(second["source"]["tracker_index"], 239)
        self.assertEqual(len(first["source"]["source_sha256"]), 64)
        self.assertEqual(result["difference"], {
            "minuend_player": "Lambo",
            "subtrahend_player": "MaxPax",
            "values": {"minerals_current": -5, "vespene_current": 0, "workers_active_count": 0},
        })
        self.assertEqual(tools.get_stats("A", 320)["difference"]["values"]["minerals_current"], 25)

    def test_rejects_invalid_and_unknown_replay_ids(self):
        """
        检查格式错误和未知回放编号能被区分。
        """
        for replay_id, code in (("../A", "invalid_replay_id"), ("Z", "unknown_replay")):
            with self.subTest(replay_id=replay_id), self.assertRaises(tools.ReplayQueryError) as raised:
                tools.get_replay_info(replay_id)
            self.assertEqual(raised.exception.code, code)

    def test_rejects_unavailable_and_invalid_frames(self):
        """
        检查未导出时刻返回可选列表，非法类型与负数被拒绝。
        """
        available = tools.get_replay_info("A")["available_game_loops"]
        with self.assertRaises(tools.ReplayQueryError) as raised:
            tools.get_stats("A", available[-1] + 1)
        self.assertEqual(raised.exception.code, "unavailable_game_loop")
        self.assertEqual(raised.exception.available_game_loops, available)
        for game_loop in (True, "160", -1):
            with self.subTest(game_loop=game_loop), self.assertRaises(tools.ReplayQueryError) as raised:
                tools.get_stats("A", game_loop)
            self.assertEqual(raised.exception.code, "invalid_game_loop")

    def test_missing_value_leaves_only_its_difference_unavailable(self):
        """
        模拟一项缺失，确认其他项和有效零值仍可使用。
        """
        stats_path = tools.PROCESSED_DIR / "A_stats_sample.csv"
        with stats_path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(tools.csv.DictReader(stream))
        row = next(row for row in rows if row["tracker_index"] == "238")
        row.update(minerals_current="", minerals_current_status="missing")
        with patch.object(tools.csv, "DictReader", return_value=iter(rows)):
            result = tools.get_stats("A", 160)
        self.assertIsNone(result["players"][0]["stats"]["minerals_current"])
        self.assertEqual(result["players"][0]["field_status"]["minerals_current"], "missing")
        self.assertEqual(result["difference"]["values"], {
            "minerals_current": None, "vespene_current": 0, "workers_active_count": 0,
        })

    def test_excludes_frame_with_duplicate_player_rows(self):
        """
        模拟统计表出现重复玩家行，确认该时点不进入可选列表。
        """
        stats_path = tools.PROCESSED_DIR / "A_stats_sample.csv"
        with stats_path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(tools.csv.DictReader(stream))
        available = tools.get_replay_info("A")["available_game_loops"]
        duplicate = next(row for row in rows if row["tracker_index"] == "238")
        with patch.object(tools.csv, "DictReader", return_value=iter([*rows, duplicate])):
            result = tools.get_replay_info("A")
        self.assertEqual(result["available_game_loops"], [frame for frame in available if frame != 160])


if __name__ == "__main__":
    main(verbosity=2)
