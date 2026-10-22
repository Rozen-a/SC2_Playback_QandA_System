import json
import sys
from pathlib import Path

# 从当前程序文件的位置出发，向上找两层目录，并把结果保存到变量 project_root 中
# __file__	当前 Python 文件的路径
# Path(__file__)	将这个路径转换成 Path 对象
# .resolve()	将路径解析为绝对路径，并解析符号链接
project_root = Path(__file__).resolve().parent.parent
# 拼接文件路径
config_path = project_root / "configs/example.json"

# 读取文件，并将 JSON 内容转换成 Python 字典
with config_path.open("r", encoding="utf-8") as file:
    # load() 接收文件对象; loads() 接收字符串
    config = json.load(file)

print("Python 路径：", sys.executable) # sys.executable 通常是当前正在运行此程序的 Python 解释器的完整路径
print("配置文件：", config_path)
print("项目名称：", config["project_name"])
print("回放编号：", config["replay_id"])
print("回答长度设置：", config["max_answer_length"])