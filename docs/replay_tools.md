# T04 回放查询工具

工具读取 `data/processed/` 下对应回放的元数据和统计表。回放编号为单个大写字母，当前已导出 A。

| 函数 | 输入 | 返回 |
| --- | --- | --- |
| `get_replay_info` | `replay_id`（字符串） | `replay_id`、按玩家编号排序的 `players`、升序排列的 `available_game_loops`。玩家信息含编号、真实姓名、种族及是否为人类玩家。 |
| `get_stats` | `replay_id`（字符串）、`game_loop`（非负整数） | `replay_id`、`game_loop`、双方的 `players` 统计和 `difference` 差值。 |

每方统计包含 `pid`、`player_name`、`stats`、`field_status` 和 `source`。三个统计字段是 `minerals_current`（矿）、`vespene_current`（气）和 `workers_active_count`（活跃工人数）。来源包含文件名 `source_file`、校验值 `source_sha256` 和 Tracker 序号 `tracker_index`。

`difference` 含 `minuend_player`、`subtrahend_player` 和 `values`。三项差值均按玩家 1 减玩家 2，保留正负号。任一方该项缺失或不可用时，统计值及对应差值以 Python 的 `None` 表示，序列化为 JSON 时为 `null`。有效零值保留为 `0`。

时刻必须同时出现在元数据的无冲突共同点和统计表中，且双方各有一条记录。扩充后 A 可查 89 个时点，前三个为 `1`、`160`、`320`。查询不可用时刻会带回可选列表。

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

## 模型工具请求

[工具请求提示](../prompts/tool_request.txt) 约定模型输出单个 JSON 对象。例如：

```json
{"tool":"get_stats","arguments":{"replay_id":"A","game_loop":160}}
```

[请求校验模块](../src/replay/tool_request.py) 只接受表中两个工具，并检查字段集合、回放编号格式和时刻类型。校验失败时，将错误原因放进修正提示，模型最多再回答一次。返回值中的 `request` 是通过校验的请求，两次都失败时为 `None`。 `attempts` 保存每次原始回答和错误说明。

JSON 校验通过后，问答流程将请求交给对应的查询工具，检查回放是否存在以及时刻是否可查。格式和查询参数共用一次修正机会。可在 IDE 中直接运行 [test_tool_request.py](../tests/test_tool_request.py)，或使用以下命令运行模拟测试。

```powershell
.\.venv\Scripts\python.exe -X utf8 .\tests\test_tool_request.py
```

## 真实模型联调

启动 T02 模型服务后，在 IDE 中选用项目的 `.venv` 解释器，直接运行 [tool_qa.py](../src/replay/tool_qa.py)，然后在终端提示处输入问题。也可以在仓库根目录运行以下命令，直接传入问题。

```powershell
.\.venv\Scripts\python.exe -X utf8 -m src.replay.tool_qa --question "回放 A 的第二个采样点，双方当前矿量分别是多少？请给出 Lambo 减 MaxPax 的差值。"
```

第二个采样点从当前可查列表定位为 `160`。核对目标是 Lambo 35、MaxPax 40、差值 `-5`，来源序号 238 和 239。指定不可查询的时刻时，流程记录失败原因及可选时刻，结束查询。

每次运行创建独立的 `results/T04/tool_qa_<UTC时间>.json`，记录模型请求与响应、校验尝试、真实查询参数与结果，以及回答或错误。

