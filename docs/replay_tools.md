# T04 回放查询工具

工具读取 `data/processed/` 下对应回放的元数据和统计表。回放编号为单个大写字母，当前已导出 A。

| 函数 | 输入 | 返回 |
| --- | --- | --- |
| `get_replay_info` | `replay_id`（字符串） | `replay_id`、按玩家编号排序的 `players`、升序排列的 `available_game_loops`。玩家信息含编号、真实姓名、种族及是否为人类玩家。 |
| `get_stats` | `replay_id`（字符串）、`game_loop`（非负整数） | `replay_id`、`game_loop`、双方的 `players` 统计和 `difference` 差值。 |

每方统计包含 `pid`、`player_name`、`stats`、`field_status` 和 `source`。三个统计字段是 `minerals_current`（矿）、`vespene_current`（气）和 `workers_active_count`（活跃工人数）。来源包含文件名 `source_file`、校验值 `source_sha256` 和 Tracker 序号 `tracker_index`。

`difference` 含 `minuend_player`、`subtrahend_player` 和 `values`。三项差值均按玩家 1 减玩家 2，保留正负号。任一方该项缺失或不可用时，统计值及对应差值以 Python 的 `None` 表示，序列化为 JSON 时为 `null`。有效零值保留为 `0`。

时刻必须同时出现在元数据的无冲突共同点和统计表中，且双方各有一条记录。当前 A 可查 `1`、`160`、`320`。查询不可用时刻会带回可选列表。

| `ReplayQueryError.code` | 情形 |
| --- | --- |
| `invalid_replay_id` | 回放编号格式错误 |
| `unknown_replay` | 对应回放尚未导出 |
| `invalid_game_loop` | 时刻为负数或类型不符 |
| `unavailable_game_loop` | 时刻不可查，异常的 `available_game_loops` 含可选时刻 |
| `invalid_data` | 数据缺少统计表，或检测到元数据、玩家、来源不一致 |

在 IDE 中选择项目的 `.venv` 解释器，打开 [test_tools.py](../tests/test_tools.py) 并运行当前 Python 文件，终端会显示六项测试结果。测试使用标准库 `unittest` 编写，也可由 `pytest` 收集。使用终端时，在仓库根目录运行以下命令。

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -p "test_tools.py" -v
```
