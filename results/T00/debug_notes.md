# 启动记录与错误排查

运行命令 `.\.venv\Scripts\python.exe .\src\read_config_example.py`

运行报错，终端信息如下

```cmd
(.venv) PS D:\rozen_file\SHU\1004\SC2_Playback_QandA_System\SC2_Playback_QandA_System> .\.venv\Scripts\python.exe .\src\read_config_example.py
Traceback (most recent call last):
  File "D:\rozen_file\SHU\1004\SC2_Playback_QandA_System\SC2_Playback_QandA_System\src\read_config_example.py", line 14, in <module>
    with config_path.open("r", encoding="utf-8") as file:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\rozen\AppData\Local\Programs\Python\Python312\Lib\pathlib.py", line 1013, in open
    return io.open(self, mode, buffering, encoding, errors, newline)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileNotFoundError: [Errno 2] No such file or directory: 'D:\\rozen_file\\SHU\\1004\\SC2_Playback_QandA_System\\SC2_Playback_QandA_System\\configs\\configs.json'
```

查看运行结果可以看到:

- 报错位置为 line 14 的 `with config_path.open("r", encoding="utf-8") as file:`
- 报错信息提示路径不存在

说明应为配置文件路径错误导致报错

阅读 python 程序对应位置发现 配置文件路径设置为

``` python
project_root = Path(__file__).resolve().parent.parent
config_path = project_root / "configs" / "configs.json"
```

而实际应为 `.\configs\example.json`

将该部分代码修改为：

```python
project_root = Path(__file__).resolve().parent.parent
config_path = project_root / "configs" / "example.json"
```

再次运行检查无误