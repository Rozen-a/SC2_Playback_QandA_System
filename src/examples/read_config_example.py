"""T00 配置读取示例，读取 JSON 并打印当前解释器和配置内容。"""

import json
import sys
from pathlib import Path

# 从当前脚本定位仓库根目录，使配置路径不受终端工作目录影响。
project_root = Path(__file__).resolve().parents[2]
config_path = project_root / "configs/example.json"

# 用 UTF-8 读取 JSON，保留示例配置中的中文。
with config_path.open("r", encoding="utf-8") as file:
    config = json.load(file)

# 打印当前解释器路径，便于确认是否正在使用项目虚拟环境。
print("Python 路径：", sys.executable)
print("配置文件：", config_path)
print("项目名称：", config["project_name"])
print("回放编号：", config["replay_id"])
print("回答长度设置：", config["max_answer_length"])
