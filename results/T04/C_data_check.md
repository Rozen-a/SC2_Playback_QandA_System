# 回放 C 数据检查记录

本文件汇总解析结果、字段一致性检查与导出范围。

- 文件：2026-10-18 - (Z)Hulk VS (P)UpK.SC2Replay
- SHA-256：08C9B11ECF76B542FCDED837F18711EA97A5A02C4790BE0F10A83BD62B04B338
- 游戏版本：5.0.17.98310；解析器版本：1.9.0
- 统计事件：41 条；排除冲突后共同采样点：20 个。
- 冲突组合：0 个。
- 全部事件三字段的检查状态计数：{'raw_matches_parser': 123}

## 导出记录（20 个采样点，40 条记录）

| 时间编号 | 玩家编号 | 玩家 | 矿 | 气 | 活跃工人数 | Tracker 序号（从 0 开始） | 三字段状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | Hulk | 50 | 0 | 12 | 273 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 1 | 2 | UpK | 50 | 0 | 12 | 274 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 160 | 1 | Hulk | 80 | 0 | 12 | 275 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 160 | 2 | UpK | 30 | 0 | 12 | 276 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 320 | 1 | Hulk | 160 | 0 | 12 | 278 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 320 | 2 | UpK | 70 | 0 | 13 | 279 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 480 | 1 | Hulk | 235 | 0 | 12 | 281 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 480 | 2 | UpK | 45 | 0 | 13 | 282 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 640 | 1 | Hulk | 305 | 0 | 12 | 284 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 640 | 2 | UpK | 80 | 0 | 14 | 285 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 800 | 1 | Hulk | 132 | 0 | 11 | 290 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 800 | 2 | UpK | 170 | 0 | 14 | 291 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 960 | 1 | Hulk | 192 | 0 | 11 | 295 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 960 | 2 | UpK | 55 | 0 | 15 | 296 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 1120 | 1 | Hulk | 262 | 0 | 11 | 299 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 1120 | 2 | UpK | 15 | 0 | 16 | 300 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 1280 | 1 | Hulk | 57 | 0 | 10 | 304 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 1280 | 2 | UpK | 70 | 0 | 17 | 305 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 1440 | 1 | Hulk | 132 | 0 | 10 | 306 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 1440 | 2 | UpK | 170 | 0 | 17 | 307 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 1600 | 1 | Hulk | 82 | 0 | 10 | 311 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 1600 | 2 | UpK | 225 | 0 | 18 | 312 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 1760 | 1 | Hulk | 7 | 0 | 10 | 320 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 1760 | 2 | UpK | 290 | 0 | 19 | 321 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 1920 | 1 | Hulk | 72 | 0 | 10 | 327 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 1920 | 2 | UpK | 405 | 8 | 20 | 328 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 2080 | 1 | Hulk | 132 | 0 | 10 | 332 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 2080 | 2 | UpK | 65 | 12 | 20 | 333 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 2240 | 1 | Hulk | 147 | 0 | 10 | 348 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 2240 | 2 | UpK | 175 | 24 | 20 | 349 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 2400 | 1 | Hulk | 172 | 0 | 10 | 353 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 2400 | 2 | UpK | 75 | 40 | 21 | 354 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 2560 | 1 | Hulk | 192 | 0 | 10 | 361 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 2560 | 2 | UpK | 190 | 60 | 21 | 362 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 2720 | 1 | Hulk | 262 | 0 | 10 | 371 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 2720 | 2 | UpK | 70 | 80 | 22 | 372 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 2880 | 1 | Hulk | 282 | 0 | 10 | 378 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 2880 | 2 | UpK | 190 | 100 | 22 | 379 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 2988 | 1 | Hulk | 277 | 0 | 10 | 390 | raw_matches_parser, raw_matches_parser, raw_matches_parser |
| 2988 | 2 | UpK | 270 | 112 | 23 | 388 | raw_matches_parser, raw_matches_parser, raw_matches_parser |

## 重复记录

- 玩家 2，时间编号 2988，事件序号 [388, 389]，冲突：False。

共同采样点数量不代表每个字段均可用。
