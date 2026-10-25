from pathlib import Path
from importlib.metadata import version
from collections import defaultdict
import sc2reader
from sc2reader.events.tracker import PlayerStatsEvent

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

    # 比较完整原始统计数组，避免遗漏其他统计字段中的差异。
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
# 此处只检查重复与冲突；缺失、异常和解析器改写检查在后续步骤完成。
