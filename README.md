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
