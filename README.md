# SC2_Playback_QandA_System
《星际争霸 II》（SC2）回放问答与模型对比系统

## T00 环境与运行

### 环境

- Windows
- Python 3.12.10
- 项目虚拟环境：.venv
- 当前配置读取程序只使用 Python 标准库，无需安装第三方依赖。

### 首次创建虚拟环境

仅在项目中不存在 .venv 时执行：

```powershell
python -m venv .venv
```

### 运行配置读取程序

```powershell
.\.venv\Scripts\python.exe .\src\read_config_example.py
```

程序读取 configs/example.json，并打印 Python 路径、配置路径和配置内容。

修改配置并保存后，再次运行即可观察变化。

### 排错记录

见 results/T00/debug_notes.md

## T01 回放解析与统计导出

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
- `results/T01/data_check.md`：自动检查报告。

以上输出会在重新运行时更新。`results/T01/manual_review.md` 是独立人工记录，程序不会覆盖；对应原始文件变化后，需要重新复核。

字段含义、缺失与异常处理见 `docs/fields.md`。当前只取前三个无冲突共同采样点；采样点存在不代表所有字段都可用，字段异常时 CSV 留空。

运行字段边界检查测试：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
```

本阶段不需要新增第三方依赖。自动检查通过后，按 `results/T01/manual_review.md` 逐条人工核对，再保存实际复核结果。



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
