# 回放 A 的 T01 自动检查记录

本文件由解析程序生成。已执行自动字段一致性检查，尚未完成独立人工复核。

- 文件：2025-11-01- (Z)Lambo VS (P)MaxPax.SC2Replay
- SHA-256：30C9F28848B5B8DE0C78E58B8A8BCF24D3377690871AC5E67CDF05673B508F19
- 游戏版本：5.0.15.95299；解析器版本：1.9.0
- 统计事件：179 条；排除冲突后共同采样点：89 个。
- 冲突组合：0 个。
- 全部事件三字段的检查状态计数：{'raw_matches_parser': 537}

## 六条样本记录

| 时间编号 | 玩家编号 | 玩家 | 矿 | 气 | 活跃工人数 | Tracker 序号（从 0 开始） | 三字段状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | Lambo | 50 | 0 | 12 | 235 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 1 | 2 | MaxPax | 50 | 0 | 12 | 236 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 160 | 1 | Lambo | 35 | 0 | 12 | 238 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 160 | 2 | MaxPax | 40 | 0 | 12 | 239 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 320 | 1 | Lambo | 40 | 0 | 13 | 246 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 320 | 2 | MaxPax | 15 | 0 | 13 | 247 | raw_matches_parser, raw_matches_parser, raw_matches_parser |

## 重复记录

- 玩家 2，时间编号 13921，事件序号 [2630, 2631]，冲突：False。

## 人工复核步骤

1. 打开 data/decoded/A_tracker_stats.json，按表中 tracker_index 找到六条事件。
2. 检查 pid、game_loop 和玩家对应关系。
3. JSON 中 raw_stats 的键为字符串；逐项查看 "0"、"1"、"4" 对应的值，与 CSV 的矿、气、活跃工人数比较。
4. 查看 field_checks：缺失、负数或改写值不能作为已确认真实值。
5. 在独立的 manual_review.md 中记录复核人、实际日期、逐条结果及问题；不要修改本自动报告伪称已人工通过。

## 文件替换情况

用户已说明先前文件错误，后用新文件替换且文件名未变。
聊天中早先记录的校验值：63BA4A0FA2C8B7DAB7630283C290973D32515DB7027C2C871A221E52CE42A2F7。
本次实际读取的校验值：30C9F28848B5B8DE0C78E58B8A8BCF24D3377690871AC5E67CDF05673B508F19。实际替换日期尚待用户补充，不能从文件时间推断。

共同采样点数量不代表每个字段均可用；程序运行成功不代表兼容所有回放。
