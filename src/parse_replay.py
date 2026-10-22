from pathlib import Path
from importlib.metadata import version
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