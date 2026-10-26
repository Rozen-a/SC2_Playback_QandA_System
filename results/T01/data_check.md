# 回放 A 的 T01 数据检查记录

本文件汇总解析与字段一致性检查结果。人工复核记录见同目录 manual_review.md。

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

## 人工复核记录

核对方法、逐条结果与复核状态见 [manual_review.md](manual_review.md)。

共同采样点数量不代表每个字段均可用；程序运行成功不代表兼容所有回放。
