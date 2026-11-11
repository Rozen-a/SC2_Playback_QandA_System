"""
T04 回放查询工具。读取已导出的 1v1 回放信息和统计记录。
"""

import csv
import json
from pathlib import Path
import re

from src.replay.stats_validation import STAT_FIELDS

PROCESSED_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"


class ReplayQueryError(ValueError):
    """
    保存查询失败的原因和可选时刻，供调用方提示用户或修正参数。
    """

    def __init__(self, code: str, message: str, *, available_game_loops: list[int] | None = None):
        """
        初始化可由调用方读取的查询错误。

        Args:
            - code (str): 可供程序判断的错误类型。
            - message (str): 面向用户的错误说明。
            - available_game_loops (list[int] | None): 查询时刻不可用时返回的可选列表。
        """
        super().__init__(message)
        self.code = code
        self.available_game_loops = available_game_loops


def _load_replay(replay_id: str) -> tuple[dict, dict[int, dict[int, dict[str, str]]]]:
    """
    读取回放信息和统计表，保留双方各有一条可信记录的共同采样点。

    Args:
        - replay_id (str): 单个大写字母形式的回放编号。

    Returns:
        - replay (tuple[dict, dict]): 回放信息，以及按时间编号和玩家编号索引的统计行。
    """
    if not isinstance(replay_id, str) or re.fullmatch(r"[A-Z]", replay_id) is None:
        raise ReplayQueryError("invalid_replay_id", "回放编号必须是单个大写字母。")

    info_path = PROCESSED_DIR / f"{replay_id}_info.json"
    stats_path = PROCESSED_DIR / f"{replay_id}_stats_sample.csv"
    try:
        info = json.loads(info_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as error:
        raise ReplayQueryError("unknown_replay", f"回放 {replay_id} 尚未导出。") from error
    if info["replay_id"] != replay_id or len(info["players"]) != 2:
        raise ReplayQueryError("invalid_data", f"回放 {replay_id} 的元数据与 1v1 查询要求不符。")

    players = sorted(info["players"], key=lambda player: player["pid"])
    names = {player["pid"]: player["name"] for player in players}
    if len(names) != 2:
        raise ReplayQueryError("invalid_data", f"回放 {replay_id} 的玩家编号重复。")
    common_frames = set(info["common_frames_after_conflict_filter"])
    by_frame = {}
    duplicate_frames = set()
    try:
        with stats_path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                frame, pid = int(row["game_loop"]), int(row["pid"])
                if (
                    row["replay_id"] != replay_id or row["source_sha256"] != info["sha256"]
                    or row["source_file"] != info["source_file"] or names.get(pid) != row["player_name"]
                ):
                    raise ReplayQueryError("invalid_data", f"回放 {replay_id} 的统计行与元数据不一致。")
                # 只保留双方各有一条可信记录的共同采样点，排除掉双方都没有可信记录的时刻。
                if frame not in common_frames:
                    continue
                # 取出 frame 对应的记录字典；如果这个帧第一次出现，就先创建一个空字典，再取出来
                # records 和 by_frame[frame] 指向同一个字典，不是两份副本
                records = by_frame.setdefault(frame, {})  
                # 解析器已经合并相同的重复事件。统计表再次出现重复行时排除整个时点。
                if pid in records:
                    duplicate_frames.add(frame)
                records[pid] = row
    except FileNotFoundError as error:
        raise ReplayQueryError("invalid_data", f"回放 {replay_id} 缺少已导出的统计表。") from error

    info["players"] = players  # 按玩家编号升序排序，方便后续计算差值
    # 过滤掉双方各有一条可信记录的时刻，保留可查询的共同采样点
    available = {
        frame: records for frame, records in sorted(by_frame.items())
        if records.keys() == names.keys() and frame not in duplicate_frames
    }
    return info, available


def get_replay_info(replay_id: str) -> dict:
    """
    查询玩家信息和当前可查询的共同采样点。

    Args:
        - replay_id (str): 回放编号，例如 A。

    Returns:
        - result (dict): 回放编号、按玩家编号排序的玩家列表和升序时间编号列表。
    """
    info, available = _load_replay(replay_id)
    return {"replay_id": replay_id, "players": info["players"], "available_game_loops": list(available)}


def get_stats(replay_id: str, game_loop: int) -> dict:
    """
    查询指定采样点的双方统计值、差值和证据来源。

    Args:
        - replay_id (str): 回放编号，例如 A。
        - game_loop (int): 非负整数形式的游戏循环编号。

    Returns:
        - result (dict): 回放编号、时间编号、双方统计值及状态、来源和玩家 1 减玩家 2 的差值。
    """
    if type(game_loop) is not int or game_loop < 0:
        raise ReplayQueryError("invalid_game_loop", "game_loop 必须是非负整数。")
    info, available = _load_replay(replay_id)
    if game_loop not in available:
        raise ReplayQueryError(
            "unavailable_game_loop", f"回放 {replay_id} 的 game_loop={game_loop} 不可查询。",
            available_game_loops=list(available),
        )

    players = []
    for player in info["players"]:
        row = available[game_loop][player["pid"]]
        statuses = {field: row[f"{field}_status"] for field in STAT_FIELDS}
        values = {}
        for field, status in statuses.items():
            # 保留有效的零值，将缺失或不可用字段映射为 None。
            values[field] = int(row[field]) if status == "raw_matches_parser" and row[field] else None
        players.append({
            "pid": player["pid"],
            "player_name": player["name"],
            "stats": values,
            "field_status": statuses,
            "source": {
                "source_file": row["source_file"],
                "source_sha256": row["source_sha256"],
                "tracker_index": int(row["tracker_index"]),
            },
        })

    first, second = players
    differences = {}
    for field in STAT_FIELDS:
        left, right = first["stats"][field], second["stats"][field]
        differences[field] = None if left is None or right is None else left - right
    return {
        "replay_id": replay_id,
        "game_loop": game_loop,
        "players": players,
        "difference": {
            "minuend_player": first["player_name"],
            "subtrahend_player": second["player_name"],
            "values": differences,
        },
    }
