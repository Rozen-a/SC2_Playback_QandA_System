# SC2_Playback_QandA_System

《星际争霸 II》（SC2）回放问答与模型对比系统。

## 项目简介

本项目围绕 SC2 游戏回放开展数据解析与整理，为后续回放问答和模型效果对比提供数据基础。项目按照任务书分阶段实现，并保存各阶段的代码、运行结果和核对记录。

当前已完成 T00 环境与配置读取，以及 T01 回放解析与统计导出。现有程序以命令行脚本运行；回放问答、模型训练与对比功能尚未实现。

### 当前功能

- 读取 JSON 配置，显示配置内容与 Python 解释器路径。
- 使用 `sc2reader` 读取回放基本信息、玩家信息和玩家统计事件。
- 检查双方共同采样点、重复记录和数据冲突。
- 核对矿、气、活跃工人数的原始统计值与解析值，区分缺失、异常与解析差异。
- 导出六条样本记录、比赛信息、完整统计核对材料和 Markdown 检查报告。

当前验证对象为回放 A（Lambo 对阵 MaxPax，游戏版本 `5.0.15.95299`）。时间字段保留为 `game_loop`，字段定义与处理规则见 [字段说明](docs/fields.md)。

## 目录结构

```text
SC2_Playback_QandA_System/
├── configs/
│   └── example.json              # 配置读取示例
├── data/
│   ├── raw/                      # 原始 .SC2Replay 文件
│   ├── decoded/
│   │   └── A_tracker_stats.json   # 已解码统计字典与字段检查结果
│   ├── processed/
│   │   ├── A_info.json            # 比赛信息与采样点摘要
│   │   └── A_stats_sample.csv     # 六条统计样本
│   └── manifest.csv              # 回放来源、校验值与版本清单
├── docs/
│   └── fields.md                 # 字段定义及异常处理规则
├── results/
│   ├── T00/                      # 环境练习与排错记录
│   └── T01/                      # 检查报告、人工复核与运行记录
├── src/
│   ├── read_config_example.py    # 配置读取入口
│   ├── parse_replay.py           # 回放解析与数据导出入口
│   ├── stats_validation.py       # 统计字段检查
│   └── report_generator.py       # Markdown 报告生成
├── tests/
│   ├── test_stats_validation.py  # 字段边界情况测试
│   └── test_export_records.py    # 导出记录对应关系测试
├── .gitignore
├── requirements.txt             # 当前使用的第三方依赖
└── README.md
```

`.venv/` 为本地虚拟环境目录，由使用者创建，不纳入版本控制。

## 安装与运行

以下命令适用于 Windows PowerShell。项目当前使用 Python `3.12.10`，依赖固定为 `sc2reader==1.9.0`。现阶段的配置读取与回放解析无需 GPU，也无需启动 SC2 游戏客户端。

### 1. 获取项目

```powershell
git clone https://github.com/Rozen-a/SC2_Playback_QandA_System.git
Set-Location .\SC2_Playback_QandA_System
```

如果已经克隆项目，直接进入包含 `src/`、`data/` 和 `requirements.txt` 的仓库根目录。后续命令均在该目录执行。

### 2. 创建环境并安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

已有 `.venv` 时跳过创建步骤。命令直接使用虚拟环境解释器，无需先激活环境。

### 3. 检查回放文件

当前解析脚本使用以下固定文件：

```text
data/raw/2025-11-01- (Z)Lambo VS (P)MaxPax.SC2Replay
```

请确认该文件存在，并与 [来源清单](data/manifest.csv) 中的文件名、SHA-256 和版本信息对应。仅重命名其他回放不能替代这一检查；如需更换回放，应同步修改脚本中的 `replay_path` 和来源清单。

### 4. 运行程序

读取示例配置：

```powershell
.\.venv\Scripts\python.exe -X utf8 .\src\read_config_example.py
```

解析回放并生成数据与报告：

```powershell
.\.venv\Scripts\python.exe -X utf8 .\src\parse_replay.py
```

运行后可查看：

| 输出 | 内容 |
| --- | --- |
| [统计样本](data/processed/A_stats_sample.csv) | 前三个无冲突共同采样点、双方共六条记录 |
| [比赛摘要](data/processed/A_info.json) | 来源、玩家、共同采样点、重复与冲突信息 |
| [统计核对材料](data/decoded/A_tracker_stats.json) | 全部玩家统计事件及字段检查结果 |
| [数据检查报告](results/T01/data_check.md) | 检查摘要与六条样本表格 |
| [人工复核记录](results/T01/manual_review.md) | 独立保存的人工核对结果，程序不会覆盖 |

重新运行会更新程序生成的数据与报告。人工复核结果只对应其记录的回放 SHA-256；更换原始回放后应重新核对。

### 5. 运行测试

先运行回放解析脚本，再执行：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
```

测试覆盖字段缺失、负数、类型异常、解析值差异，以及导出样本与原始统计材料的对应关系。若未生成统计核对材料，导出记录测试会跳过。

## 按任务书的实施记录

以下保留各任务的操作说明与阶段记录。

### T00 环境与运行

#### 环境

- Windows
- Python 3.12.10
- 项目虚拟环境：.venv
- 当前配置读取程序只使用 Python 标准库，无需安装第三方依赖。

#### 首次创建虚拟环境

仅在项目中不存在 .venv 时执行：

```powershell
python -m venv .venv
```

#### 运行配置读取程序

```powershell
.\.venv\Scripts\python.exe .\src\read_config_example.py
```

程序读取 configs/example.json，并打印 Python 路径、配置路径和配置内容。

修改配置并保存后，再次运行即可观察变化。

#### 排错记录

见 results/T00/debug_notes.md

### T01 回放解析与统计导出

代码职责：`src/parse_replay.py` 负责解析与数据导出，`src/stats_validation.py` 负责字段检查，`src/report_generator.py` 负责将检查结果整理成 Markdown 报告。报告模块通过 `write_t01_report` 接收数据，不自行解析回放。

在项目根目录执行。当前支持范围仅为本次已验证的回放 A，不代表所有版本都兼容。

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -X utf8 .\src\parse_replay.py
```

程序读取 `data/raw` 中代码指定的回放，并核对 `data/manifest.csv` 中的 SHA-256、游戏版本和解析器版本。更换回放时必须核实来源清单，不能仅复用同名旧文件的记录。

执行后生成：

- `data/processed/A_stats_sample.csv`：三个共同采样点、双方共六条记录。
- `data/processed/A_info.json`：比赛、玩家、共同采样点及重复冲突摘要。
- `data/decoded/A_tracker_stats.json`：全部原始统计字典及字段检查结果。
- `results/T01/data_check.md`：数据检查报告。

以上输出会在重新运行时更新。`results/T01/manual_review.md` 是独立人工记录，程序不会覆盖；对应原始文件变化后，需要重新复核。

字段含义、缺失与异常处理见 `docs/fields.md`。当前只取前三个无冲突共同采样点；采样点存在不代表所有字段都可用，字段异常时 CSV 留空。

运行字段边界检查测试：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
```

本阶段不需要新增第三方依赖。人工复核结果保存在 `results/T01/manual_review.md`。



> ## 数据来源与官方资料
>
> **[1]** **回放下载入口** Spawning Tool 回放列表；示例页面含 Download Replay。
>
> https://lotv.spawningtool.com/replays/
>
> https://lotv.spawningtool.com/82317/
>
> **[2] sc2reader** 回放解析与 tracker 事件读取。
>
> https://github.com/ggtracker/sc2reader
>
> **[3]** **统计字段代码** PlayerStatsEvent 字段、时间字段和原始统计值。
>
> https://github.com/ggtracker/sc2reader/blob/upstream/sc2reader/events/tracker.py
>
> **[4] Qwen3-1.7B** 候选模型、加载方式与思考模式设置。
>
> https://huggingface.co/Qwen/Qwen3-1.7B
>
> **[5] LangChain** 连接模型、提示和工具的官方说明。
>
> https://docs.langchain.com/oss/python/langchain/overview
>
> **[6] LangGraph** 节点、状态与流程控制的官方说明。
>
> https://docs.langchain.com/oss/python/langgraph/overview
>
> **[7]** **中文文本向量模型** bge-small-zh-v1.5 及使用方式。
>
> https://huggingface.co/BAAI/bge-small-zh-v1.5
>
> **[8] PEFT** LoRA 等附加参数的训练、保存与加载。
>
> https://huggingface.co/docs/peft/quicktour
>
> **[9] TRL** SFTTrainer 的样本组织与训练方式。
>
> https://huggingface.co/docs/trl/sft_trainer
>
> **[10]** **输出蒸馏** Kim 与 Rush，Sequence-Level Knowledge Distillation，2016。
>
> https://arxiv.org/abs/1606.07947
>
> **[11] Gradio** 官方项目：用 Python 函数构建应用界面。
>
> https://github.com/gradio-app/gradio
>
> **[12] s2protocol** Blizzard 底层回放协议参考，按需查阅。
>
> https://github.com/Blizzard/s2protocol
>
> **[13] VS Code Python** **入门** 环境选择、运行与调试示例。
>
> https://code.visualstudio.com/docs/python/python-tutorial
