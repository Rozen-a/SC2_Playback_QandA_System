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

见 results/T00/debug_notes.md。
