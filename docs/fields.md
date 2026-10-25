# 回放统计字段与处理规则

本阶段读取正常 1v1 回放中的 PlayerStatsEvent。当前样本来自回放 A；不据此声称支持所有回放。

## 字段对应

| 导出字段 | 来源 | 含义 |
| --- | --- | --- |
| pid | event.pid | 统计事件所属的玩家编号，对应 replay.players 中的 pid |
| player_name | player.name | 真实玩家名，不依靠文件名猜测 |
| game_loop | event.frame | 本项目保存的时间编号，不直接解释为比赛秒数 |
| minerals_current | event.stats[0] 与 event.minerals_current | 玩家当前可用的矿 |
| vespene_current | event.stats[1] 与 event.vespene_current | 玩家当前可用的气 |
| workers_active_count | event.stats[4] 与 event.workers_active_count | 活跃工人数，不能自行解释为正在采矿的工人数 |
| tracker_index | enumerate(replay.tracker_events) | 从 0 开始的 Tracker 列表位置；不是游戏事件自身提供的全局唯一编号 |
| source_file 与 source_sha256 | 原始文件名与实际计算值 | 确定这条记录来自哪份原始文件 |

字段依据：项目所安装 sc2reader 1.9.0 的 events/tracker.py 中 PlayerStatsEvent.__init__。该回放实际解码得到的 event.stats 是整数键字典；JSON 导出后键为字符串，例如 raw_stats["0"]。不得使用 list(event.stats) 导出值，否则得到的是键。
上游参考：https://github.com/ggtracker/sc2reader/blob/upstream/sc2reader/events/tracker.py 。上游可能变化，实施以本地固定版本为准。

## 时间、重复与冲突

- 先按 (pid, frame) 分组。完整原始统计数组不同则标记冲突，该组合不参与查询。
- 完整原始统计数组相同的重复事件，选择第一条参与查询，同时保留全部事件和序号以供核对。
- 共同采样点是双方排除冲突后的时间编号交集，按升序排列。本阶段选前三个不同编号，不做任意秒查询、最近点替代或插值。
- 共同点只代表双方都有无冲突记录，不代表每项字段均可用。

## 缺失、异常和解析器改写

sc2reader 1.9.0 对三项目标字段调用 clamp，将负数限制为 0；因此不能只保存解析后的属性。

| 状态 | 条件 | 整理后值 |
| --- | --- | --- |
| raw_matches_parser | 原始值为非负整数，且与解析值一致 | 保留原始值，仍需人工复核来源 |
| missing | 原始值不存在或为 None | JSON 用 null；CSV 留空 |
| invalid_raw | 原始值为负数，或不是整数 | 留空；原始值和解析值仍保留在核对材料中 |
| parser_mismatch | 原始值为非负整数，但解析值不同 | 留空，等待核实 |

检查每个字段是否被解析器改写，结果保存在 field_checks 的 parser_changed。不会以零代替缺失或异常；本阶段不计算差值。

本检查在回放成功解码后执行。若底层解析器在构造事件时因格式错误失败，本程序会报错，不保证能修复损坏回放。

## 输出与复核

- data/processed/A_stats_sample.csv：两个玩家、三个采样点，共六条记录。
- data/processed/A_info.json：比赛信息、玩家映射、共同点和重复冲突摘要。
- data/decoded/A_tracker_stats.json：全部玩家统计事件的原始统计字典、解析字段与检查状态。这里“原始”指已解码但尚未 clamp 的统计字典，不是原始回放字节。
- results/T01/data_check.md：可重复生成的自动检查报告，不能作为人工复核签字记录。

用 CSV 中的 tracker_index 定位 JSON 事件，逐项比较玩家、时间和 raw_stats 的 "0"、"1"、"4" 键对应值；人工结果另存 results/T01/manual_review.md。
