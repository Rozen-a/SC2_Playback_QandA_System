from pathlib import Path
from importlib.metadata import version
from collections import defaultdict
import csv
import hashlib
import json
import sc2reader
from sc2reader.events.tracker import PlayerStatsEvent
from stats_validation import STAT_FIELDS, check_stat
from report_generator import write_t01_report

project_root = Path(__file__).resolve().parent.parent
replay_path = project_root / r"data\raw\2025-11-01- (Z)Lambo VS (P)MaxPax.SC2Replay"

# 检查基本配置
print("\n","="*50)
print("基本配置检查")
print("-"*50)
print("sc2reader 版本：", version("sc2reader"))
print("回放文件路径：", replay_path)

print("\n","="*50)
print("回放信息概览")
print("-"*50)
# 加载回放，不加载地图文件
replay = sc2reader.load_replay(str(replay_path), load_map=False)

print("游戏版本：", replay.release_string)
print("地图名称：", replay.map_name)
print("比赛类型：", replay.type)
print("实际队伍类型：", replay.real_type)
print("玩家数量：", len(replay.players))
print("回放总时间编号：", replay.frames)

print("\n","="*50)
print("玩家信息")
print("-"*50)
for player in replay.players:
    print(
        f"玩家编号={player.pid}，"
        f"名称={player.name}，"
        f"种族={player.play_race}，"
        f"是否人类玩家={player.is_human}"
    )

print("\n","="*50)
print("Tracker 事件分析")
print("-"*50)
# 从全部 tracker 事件中筛选玩家统计事件
# 逐个遍历回放中的 Tracker 事件，判断当前事件是否为 PlayerStatsEvent 类型或其子类，把符合条件的事件对象放进列表
stats_events = [
    event
    for event in replay.tracker_events
    if isinstance(event, PlayerStatsEvent)
]

print("\nTracker 事件总数：", len(replay.tracker_events))
print("玩家统计事件数量：", len(stats_events))

if stats_events:
    first_event = stats_events[0]
    print("首条统计事件的玩家编号：", first_event.pid)
    print("首条统计事件的时间编号：", first_event.frame)
else:
    print("未找到玩家统计事件，需要检查回放和解析兼容性")

print("\n", "=" * 50)
print("共同采样点检查")
print("-" * 50)

# 按玩家编号和时间编号分组，保留全部原始事件及其位置
# 同一个玩家、同一个时间编号，可能对应多条事件，用字典保存
grouped_events = defaultdict(list)

# enumerate() 每次提供两个值：
# - tracker_index：当前事件的序号，从 0 开始
# - event：当前事件对象
for tracker_index, event in enumerate(replay.tracker_events):
    # 只处理 PlayerStatsEvent 类型的事件
    if isinstance(event, PlayerStatsEvent):
        key = (event.pid, event.frame)
        grouped_events[key].append((tracker_index, event))

# 同一玩家、同一时刻出现不同记录时标记冲突
usable_events = {} # 通过冲突检查的事件
conflict_keys = [] # 存在统计数据冲突的分组
for key, records in grouped_events.items():
    first_event = records[0][1]

    # 比较完整原始统计字典，避免遗漏其他统计字段中的差异。
    has_conflict = any(
        event.stats != first_event.stats
        for _, event in records[1:]
    )

    if has_conflict:
        conflict_keys.append(key)
        print("发现冲突，暂不使用：", key)
    else:
        # 完全相同的重复记录只取第一条参与查询；全部记录仍保留在分组中。
        usable_events[key] = records[0]

    if len(records) > 1:
        print(
            "重复记录：", key,
            "条数：", len(records),
            "是否冲突：", has_conflict,
        )

# 检查回放类型和玩家数量，确保只处理两个参赛玩家的 1v1 回放
player_ids = [player.pid for player in replay.players]
if replay.real_type != "1v1" or len(player_ids) != 2:
    raise ValueError("当前程序只处理两个参赛玩家的 1v1 回放。")

# 统计每个玩家的无冲突采样点数量
sampling_points = []
for pid in player_ids:
    frames = {
        frame
        for player_id, frame in usable_events
        if player_id == pid
    }
    sampling_points.append(frames)
    print(f"玩家 {pid} 的无冲突采样点数量：{len(frames)}")

# 取双方时间编号的交集，再按升序排列。
common_frames = sorted(sampling_points[0] & sampling_points[1])
print("冲突的玩家与时间组合数量：", len(conflict_keys))
print("无冲突共同采样点数量：", len(common_frames))
print("前 10 个共同采样点：", common_frames[:10])

if len(common_frames) < 3:
    raise ValueError("不足三个无冲突共同采样点，需要进一步检查。")

selected_frames = common_frames[:3]
print("本次准备核对的三个采样点：", selected_frames)

print("\n", "=" * 50)
print("统计字段检查与导出")
print("-" * 50)

# 用当前文件的校验值检查来源清单，避免误用同名的旧文件。
replay_sha256 = hashlib.sha256(replay_path.read_bytes()).hexdigest().upper()
manifest_path = project_root / "data/manifest.csv"
with manifest_path.open("r", encoding="utf-8-sig", newline="") as file:
    manifest_rows = list(csv.DictReader(file)) # 使用表头作为键，把每一行读成字典，并将所有行收集成列表
matches = [row for row in manifest_rows if row["filename"] == replay_path.name]
if len(matches) != 1:
    raise ValueError("来源清单中必须有且只有一条对应当前文件名的记录。")
manifest_record = matches[0]
if manifest_record["sha256"].upper() != replay_sha256:
    raise ValueError("当前回放校验值与来源清单不同，请先核实文件替换记录。")
if manifest_record["parser_version"] != version("sc2reader"):
    raise ValueError("来源清单中的解析器版本与当前环境不同，请先核实。")
if manifest_record["game_version"] != replay.release_string:
    raise ValueError("来源清单中的游戏版本与当前回放不同，请先核实。")
replay_id = manifest_record["replay_id"]
# replay_id 将用于导出文件名，只允许简单编号，避免误生成到其他目录。
if not replay_id or not all(char.isascii() and (char.isalnum() or char in "_-") for char in replay_id):
    raise ValueError("回放编号只能包含英文字母、数字、下划线和短横线。")

# 创建字典，将玩家编号映射到玩家对象
players = {player.pid: player for player in replay.players}
decoded_records = [] # 按事件序号顺序的统计事件列表
decoded_by_index = {} # 按事件序号索引的统计事件
quality_counts = defaultdict(int) # 统计字段检查状态计数

# 导出全部统计事件，包括重复和冲突事件；不覆盖或修改事件原始统计字典。
for tracker_index, event in enumerate(replay.tracker_events):
    if not isinstance(event, PlayerStatsEvent):
        continue
    checks = {} # 每个字段的检查结果
    for field, raw_index in STAT_FIELDS.items():
        raw_value = event.stats.get(raw_index) # 获取原始统计字典中指定索引的值，如果不存在则返回 None
        parsed_value = getattr(event, field, None) # 获取解析器处理后的值，如果不存在则返回 None
        checks[field] = check_stat(raw_value, parsed_value)
        quality_counts[checks[field]["status"]] += 1
    record = {
        "tracker_index": tracker_index,
        "pid": event.pid,
        "game_loop": event.frame,
        "player_name": players[event.pid].name if event.pid in players else None,
        # 本版本的 stats 实际是整数键字典；JSON 会把键转换成字符串。
        # 不能用 list(event.stats)，那样保存的会是键而不是统计值。
        "raw_stats": dict(event.stats),
        "field_checks": checks,
        "conflict": (event.pid, event.frame) in conflict_keys,
    }
    decoded_records.append(record)
    decoded_by_index[tracker_index] = record

# 将三个采样点的双方记录整理成六行，保留事件序号以便回查。
sample_rows = []
for frame in selected_frames:
    for pid in player_ids:
        tracker_index, event = usable_events[(pid, frame)]
        checks = decoded_by_index[tracker_index]["field_checks"]
        row = {
            "replay_id": replay_id,
            "game_loop": frame,
            "pid": pid,
            "player_name": players[pid].name,
            **{field: checks[field]["value"] for field in STAT_FIELDS},
            **{field + "_status": checks[field]["status"] for field in STAT_FIELDS},
            "tracker_index": tracker_index,
            "duplicate_count": len(grouped_events[(pid, frame)]),
            "source_file": replay_path.name,
            "source_sha256": replay_sha256,
        }
        sample_rows.append(row)
        print(
            f"时间编号={frame}，玩家={players[pid].name}，"
            f"矿={row['minerals_current']}，气={row['vespene_current']}，"
            f"活跃工人数={row['workers_active_count']}，事件序号={tracker_index}"
        )

# 创建导出目录，确保存在
processed_dir = project_root / "data/processed"
decoded_dir = project_root / "data/decoded"
results_dir = project_root / "results/T01"
for directory in (processed_dir, decoded_dir, results_dir):
    directory.mkdir(parents=True, exist_ok=True)

# 导出原始统计字典、样本 CSV、信息 JSON 和自动检查报告
source = {
    "replay_id": replay_id,
    "source_file": replay_path.name,
    "sha256": replay_sha256,
    "source_url": manifest_record["source_url"],
    "download_date_as_recorded": manifest_record["download_date"],
    "game_version": replay.release_string,
    "parser_version": version("sc2reader"),
}
info = {
    **source,
    "map_name": replay.map_name,
    "real_type": replay.real_type,
    "total_game_loops": replay.frames,
    "players": [
        {"pid": pid, "name": players[pid].name,
         "race": players[pid].play_race, "is_human": players[pid].is_human}
        for pid in player_ids
    ],
    "common_frames_after_conflict_filter": common_frames,
    "selected_frames": selected_frames,
    "conflict_keys": conflict_keys,
    "duplicate_groups": [
        {"pid": key[0], "game_loop": key[1],
         "tracker_indices": [index for index, _ in records],
         "conflict": key in conflict_keys}
        for key, records in grouped_events.items() if len(records) > 1
    ],
    "field_status_counts_all_events": dict(quality_counts),
    "note": "共同点已排除冲突；每字段仍须检查状态。自动一致性检查不代替人工复核。",
}

sample_path = processed_dir / f"{replay_id}_stats_sample.csv"
with sample_path.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=list(sample_rows[0]))
    writer.writeheader()
    writer.writerows(sample_rows)  # None 在 CSV 中写成空白，绝不写成零。

info_path = processed_dir / f"{replay_id}_info.json"
info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
raw_path = decoded_dir / f"{replay_id}_tracker_stats.json"
raw_path.write_text(json.dumps({
    "source": source,
    "tracker_index_base": 0,
    "raw_stats_meaning": "PlayerStatsEvent.stats，已解码但未进行字段 clamp 的原始统计字典；不是原始二进制字节。JSON 键为字符串。",
    "field_raw_indices": STAT_FIELDS,
    "events": decoded_records,
}, ensure_ascii=False, indent=2), encoding="utf-8")

# 报告排版与写入由独立模块负责，解析程序只传递已经检查过的数据。
report_path = write_t01_report(
    info=info,
    sample_rows=sample_rows,
    stats_event_count=len(decoded_records),
    output_dir=results_dir,
)
print("全部统计事件的字段检查计数：", dict(quality_counts))
for path in (sample_path, info_path, raw_path, report_path):
    print("已导出：", path.relative_to(project_root))
print("下一步：按 data_check.md 的步骤人工复核六条记录。")
