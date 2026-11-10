"""T02 端到端验收，覆盖生成长度、请求异常和服务重启。

运行前请保持服务端口空闲。脚本启动本地模型服务，用独立客户端发起真实请求，
将结果保存到 acceptance.json，将两次启动的服务日志写入 restart_service.log。
脚本只管理自己创建的服务进程。
"""

from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time
from uuid import uuid4
from urllib.error import URLError
from urllib.request import urlopen


# 从脚本位置定位仓库根目录，使配置和脚本路径不受调用目录影响。
ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT / "configs/model.json").read_text(encoding="utf-8"))
HOST, PORT = CONFIG["service"]["host"], CONFIG["service"]["port"]
BASE_URL = f"http://{HOST}:{PORT}"


def get_health() -> dict:
    """查询当前服务的健康接口。

    Returns:
        - state (dict): 健康响应，含模型版本、设备、加载耗时（秒）及服务进程编号。
    """
    with urlopen(BASE_URL + "/health", timeout=2) as response:
        return json.load(response)


def wait_until_closed():
    """轮询端口，确认旧服务停止监听后才继续验收。"""
    for _ in range(40):
        with socket.socket() as probe:  # socket.socket() 默认创建一个用于 IPv4 TCP 通信的套接字；命名为 probe
            if probe.connect_ex((HOST, PORT)) != 0:  # connect_ex()尝试连接，返回 0 表示连接成功
                return
        time.sleep(0.1)
    raise RuntimeError("模型服务端口仍在监听。")


def verify(output_dir: Path):
    """执行长度比较、异常处理和重启检查，保存结果并清理服务。

    Args:
        - output_dir (Path): 仓库内的验收输出目录。
          已存在的同名汇总和服务日志会被覆盖。
    """
    # 在写入本次输出或启动新进程前，确认目标地址属于本机且端口空闲。
    if HOST != "127.0.0.1":
        raise ValueError("验收只能连接本机模型服务。")
    with socket.socket() as probe:
        if probe.connect_ex((HOST, PORT)) == 0:
            raise RuntimeError(f"{BASE_URL} 已在运行，请先停止该服务再执行验收。")
    # parents=True：如果上级目录不存在，也一起创建。
    # exist_ok=True：如果目标目录已经存在，就继续运行，不报错。
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "acceptance.json"  # 汇总验收状态、各个用例结果和健康信息
    service_log = output_dir / "restart_service.log"  # 保存本次验收中两轮服务启动的日志
    # 客户端每次先写临时 JSON，汇总到报告后由本脚本清理。
    temp_output = output_dir / f".client_{uuid4().hex}.json"  # uuid4().hex 生成随机标识
    service_log.write_text("", encoding="utf-8")  # 清空同名服务日志
    env = os.environ.copy()  # 复制当前环境变量
    env.update(
        PYTHONIOENCODING="utf-8",
        PYTHONDONTWRITEBYTECODE="1",
        HF_HUB_DISABLE_PROGRESS_BARS="1",
        TQDM_DISABLE="1",
    )
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "in_progress",
        "model_config": CONFIG,
        "base_url": BASE_URL,
        "cases": {},
        "scope": "真实模型与独立客户端的长度、错误参数、超时、繁忙、停止和重启检查；未制造GPU故障以触发HTTP 500。",
    }
    owned = None  # 此时还没有本脚本创建的服务子进程
    log_offset = 0  # 标记当前这轮启动日志从哪里开始

    def own_server_pid():
        """从本轮启动日志识别实际服务进程。

        Returns:
            - pid (int | None): 实际服务 PID，尚未找到启动行时为 None。
        """
        # Windows 虚拟环境启动器的 PID 可能与实际服务不同，只扫描本次启动写入的日志。
        session_log = service_log.read_bytes()[log_offset:].decode("utf-8", errors="replace")
        # 搜索形如 Started server process [数字] 的启动行。正则中的 (\d+) 捕获方括号里的进程编号，也就是 PID。
        match = re.search(r"Started server process \[(\d+)\]", session_log)
        return int(match.group(1)) if match else None

    def stop_service():
        """只停止本脚本启动的服务，并等待端口释放。"""
        # `nonlocal` 表示它要修改的是外层 verify() 中的 owned。否则，后面的 owned = None 会被当作对一个新局部变量赋值。
        nonlocal owned

        # 没有要管理的服务，直接返回
        if owned is None:
            return
        # 如果本轮服务还在运行，尝试通过 PID 停止它。若 PID 还没写入日志，直接终止子进程。
        if owned.poll() is None:
            pid = own_server_pid()
            if pid is None:
                # 服务尚未写出启动行时，通过本脚本持有的子进程句柄停止它。
                owned.terminate()
            else:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        # 等待服务进程退出并确认端口释放。若服务已退出，owned.poll() 会返回非 None。
        owned.wait(timeout=10)
        wait_until_closed()
        owned = None

    def start_service():
        """启动模型服务，等待加载完成并核对响应进程。

        Returns:
            - state (dict): 本轮服务的健康响应，含模型版本、设备及进程编号。
        """
        nonlocal owned, log_offset
        # 两次启动共用一个日志文件，用文件字节偏移区分各轮输出。
        log_offset = service_log.stat().st_size
        with service_log.open("a", encoding="utf-8") as log:
            # 用当前 Python 解释器启动服务脚本。`cwd=ROOT` 设置子进程的工作目录；标准输出和标准错误都写入服务日志。`Popen()` 启动后就返回，所以验收脚本可以接着检查服务是否就绪
            owned = subprocess.Popen(
                [sys.executable, "-X", "utf8", "-B", "src/model/model_service.py"],
                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=env,
            )

        deadline = time.monotonic() + 75  # 轮询截止时间
        while time.monotonic() < deadline:
            if owned.poll() is not None:  # poll() 返回 None 表示子进程仍在运行
                raise RuntimeError(f"模型服务启动失败，请查看 {service_log}。")
            try:
                state = get_health()
            except (URLError, TimeoutError):  # health 暂时连不上或超时：等 0.5 秒再试。
                time.sleep(0.5)
                continue
            if state["process_id"] != own_server_pid():
                raise RuntimeError("健康响应来自其他进程，停止验收。")
            return state
        raise TimeoutError("模型服务启动超时。")

    def save():
        """把当前验收状态和已收集的结果写入汇总文件。"""
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def invoke(name, *args, expected_code=None, keep=True):
        """在独立进程中运行客户端，读取实际调用记录。

        Args:
            - name (str): 用例名称，作为汇总报告中的键。
            - *args (str): 传给客户端的额外命令行参数。
            - expected_code (int | None): 预期退出码，为 None 时不检查。
            - keep (bool): 是否按名称把本次结果写入验收汇总。

        Returns:
            - result (dict): 客户端生成的调用记录，附带 client_exit_code。
        """
        # 清除上一次请求的临时结果，避免客户端提前退出时读取到旧记录。
        temp_output.unlink(missing_ok=True)
        command = [sys.executable, "-X", "utf8", "-B", "src/model/model_client.py", *args, "--output", str(temp_output)]
        # subprocess.run() ：启动一个子进程，等待它运行结束，再把运行结果交回给当前程序。
        # 正常返回时，`run` 是一个 CompletedProcess 对象。脚本用到它的三个属性：
        # - run.returncode：客户端退出码。这个项目用 0 表示调用成功，`1` 表示已处理的调用失败。
        # - run.stdout：客户端打印的正常输出。
        # - run.stderr：客户端打印的错误输出。
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", env=env, timeout=65)
        if not temp_output.exists():
            raise RuntimeError(f"客户端未生成记录：{run.stdout}\n{run.stderr}")
        result = json.loads(temp_output.read_text(encoding="utf-8"))
        result["client_exit_code"] = run.returncode
        if keep:
            report["cases"][name] = result
            save()
        if expected_code is not None:
            assert run.returncode == expected_code, (name, result)
        return result

    try:
        # 启动服务，检查健康响应中的模型标识和 revision 是否与配置一致，并要求设备是 cuda:0
        before = start_service()
        assert before["model_id"] == CONFIG["model_id"] and before["revision"] == CONFIG["revision"]
        assert before["device"] == "cuda:0"
        report["health_before"] = before
        save()

        # 1 第一轮验收：正常生成、长度限制和异常恢复

        # 先预热模型，再使用同一个问题对比两种生成上限，减少首次调用开销的影响。
        prompt = "请写一段约300字的中文说明，介绍人工智能的定义、常见应用和局限。"
        invoke("warmup", "--prompt", prompt, "--max-new-tokens", "8", expected_code=0)  # 上限 8 token
        # 用同一个问题分别生成两次，分别限制 32 和 128 token，检查生成长度是否符合预期。
        short = invoke("length_32", "--prompt", prompt, "--max-new-tokens", "32", expected_code=0)
        long = invoke("length_128", "--prompt", prompt, "--max-new-tokens", "128", expected_code=0)
        # 核对套用对话模板后的输入一致，并检查每次生成是否遵守对应的 token 上限。
        assert short["response"]["rendered_prompt"] == long["response"]["rendered_prompt"]
        assert short["response"]["input_tokens"] == long["response"]["input_tokens"]
        for case, limit in ((short, 32), (long, 128)):
            assert 0 < case["response"]["generated_tokens"] <= limit
            assert case["response"]["revision"] == CONFIG["revision"]
            assert not case["response"]["enable_thinking"]
        print("长度比较：", [(c["response"]["generated_tokens"], c["response"]["generation_seconds"]) for c in (short, long)], flush=True)

        # 用零长度触发参数校验失败，核对客户端记录的 HTTP 422。
        invalid = invoke("invalid_length", "--max-new-tokens", "0", expected_code=1)
        assert invalid["error"]["kind"] == "http_error" and invalid["error"]["http_status"] == 422
        # 用较长的生成请求和很短的等待时间触发客户端超时。
        # 超时后服务端仍可能生成，此时下一次请求应收到表示忙碌的 HTTP 503。
        timeout = invoke(
            "timeout", "--prompt", "请写一篇较长的中文文章，详细介绍人工智能的发展、应用、优势和局限，不要只给一句话。",
            "--max-new-tokens", "512", "--timeout", "0.02", expected_code=1,
        )
        assert timeout["error"]["kind"] == "timeout", timeout
        busy = invoke("busy_after_timeout", expected_code=1)
        assert busy["error"]["http_status"] == 503, busy
        print("错误参数422、实际请求超时、后台生成期间503检查通过。", flush=True)

        # 等待已超时请求的后台生成结束，避免把“仍忙碌”误判为恢复失败。
        deadline = time.monotonic() + 45
        retries = 0  # 记录在后台生成结束前，客户端收到 503 的次数
        while True:
            # 轮询调用恢复探针，直到后台生成结束并能成功返回。
            time.sleep(0.5)
            recovered = invoke("recovery_probe", keep=False)
            if recovered["success"]:
                report["cases"]["after_timeout"] = recovered
                report["busy_retries_before_recovery"] = retries
                save()
                break
            assert recovered["error"]["http_status"] == 503, recovered
            retries += 1
            if time.monotonic() > deadline:
                raise TimeoutError("后台生成结束后未恢复调用。")

        # 第二轮验收。先在端口释放后发起请求，验证客户端能识别连接失败。
        stop_service()
        report["original_service_stopped"] = True
        unavailable = invoke("while_stopped", expected_code=1)
        assert unavailable["error"]["kind"] == "connection_error"
        print("服务停止后，独立客户端明确报告连接失败。", flush=True)

        # 核对新进程加载了同一版本模型，再用独立客户端验证生成已恢复。
        restarted_health = start_service()
        assert restarted_health["process_id"] != before["process_id"]
        assert restarted_health["revision"] == before["revision"] and restarted_health["device"] == "cuda:0"
        report["health_after_restart"] = restarted_health
        restarted = invoke("after_restart", expected_code=0)
        assert restarted["success"] and restarted["response"]["revision"] == CONFIG["revision"]
        print("重启后客户端调用成功，新进程：", restarted_health["process_id"], flush=True)
        stop_service()
        report["test_service_stopped"] = True
        report["shutdown_method"] = "终止脚本启动的服务进程。"
        report["status"] = "passed"
        report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    except Exception as error:
        report["status"] = "failed"
        report["failure"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        # 无论断言是否通过，都尝试停止本次启动的服务，并保存已收集的结果。
        try:
            stop_service()
        finally:
            save()
            temp_output.unlink(missing_ok=True)
    print("验收状态：", report["status"], flush=True)
    print("测试服务已停止；汇总记录：", report_path, flush=True)


def main():
    """解析仓库内的输出位置并运行验收。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="results/T02", help="仓库内的输出目录（同名记录会覆盖）")
    args = parser.parse_args()
    output_dir = (ROOT / args.output_dir).resolve()
    if not output_dir.is_relative_to(ROOT):
        parser.error("验收输出目录必须在仓库内。")
    verify(output_dir)


if __name__ == "__main__":
    main()
