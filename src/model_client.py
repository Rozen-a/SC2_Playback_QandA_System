"""T02：通过 HTTP 调用本地模型服务，显示结果并保存调用记录。

职责：读取调用配置、发送问题、处理通信错误；模型加载与生成由服务端负责。
"""

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ModelClientError(RuntimeError):
    """携带错误类别、HTTP 状态和服务端详情，供调用方显示与记录。"""

    def __init__(self, kind: str, message: str, *, status_code=None, detail=None):
        """保留可读提示及结构化信息，不将调用失败包装成模型回答。"""
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code
        self.detail = detail


def request_answer(service_url: str, payload: dict, timeout_seconds: float) -> dict:
    """发送一次生成请求；成功返回响应与请求耗时，失败抛出 ModelClientError。"""
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ModelClientError("invalid_timeout", "超时设置必须是大于 0 的有限秒数。")

    started = time.perf_counter()
    try:
        # 本机服务直接连接，避免环境中的代理设置干扰回环地址。
        with requests.Session() as session:
            session.trust_env = False
            # 发送 POST 请求，包含 JSON 数据和超时设置
            response = session.post(
                service_url.rstrip("/") + "/generate",
                json=payload,
                timeout=timeout_seconds,
            )
    except requests.Timeout as error:
        # 客户端停止等待不会取消服务端已开始的 GPU 生成。
        raise ModelClientError("timeout", "等待服务响应超时；服务端可能仍在生成，请稍后再试。") from error
    except requests.ConnectionError as error:
        raise ModelClientError(
            "connection_error", "无法连接模型服务，请确认服务已启动、加载完成且地址端口正确。"
        ) from error
    except requests.RequestException as error:
        raise ModelClientError("request_error", f"HTTP 请求失败：{error}") from error
    elapsed = round(time.perf_counter() - started, 3)

    try:
        # 将 HTTP 响应正文解析为 Python 对象
        data = response.json()
    except requests.exceptions.JSONDecodeError as error:
        raise ModelClientError(
            "invalid_response", "服务返回的内容不是有效 JSON。", status_code=response.status_code
        ) from error

    # 检查 HTTP 状态码，非 200 视为调用失败，返回服务端提供的错误详情。
    if response.status_code != 200:
        messages = {
            422: "请求参数不符合服务要求，请查看错误详情。",
            503: "模型正在生成其他回答，请稍后重试。",
            500: "服务端生成失败，请查看模型服务日志。",
        }
        raise ModelClientError(
            "http_error",
            messages.get(response.status_code, "模型服务返回了 HTTP 错误。"),
            status_code=response.status_code,
            detail=data.get("detail", data) if isinstance(data, dict) else data,
        )

    # 检查关键返回字段，避免把错误页面或缺少回答的 JSON 当作调用成功。
    if not isinstance(data, dict) or not isinstance(data.get("answer"), str) or not data["answer"].strip():
        raise ModelClientError("invalid_response", "服务响应缺少有效回答。", status_code=200)
    tokens, seconds = data.get("generated_tokens"), data.get("generation_seconds")
    if (
        type(tokens) is not int or tokens <= 0
        or type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0
    ):
        raise ModelClientError("invalid_response", "服务响应缺少有效的生成长度或耗时。", status_code=200)
    return {"http_status": response.status_code, "request_seconds": elapsed, "response": data}


def main() -> int:
    """提供独立命令行入口；成功返回 0，调用失败记录原因并返回 1。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/model.json", help="相对于仓库根目录的配置路径")
    parser.add_argument("--prompt", default="请用一句简短的中文介绍你自己。", help="发送给模型的问题")
    parser.add_argument("--max-new-tokens", type=int, help="新增 token 上限，省略时使用配置值")
    parser.add_argument("--timeout", type=float, help="连接和读取等待超时秒数，省略时使用配置值")
    parser.add_argument("--output", default="results/T02/client_inference.json", help="调用记录保存位置")
    args = parser.parse_args()

    config = json.loads((PROJECT_ROOT / args.config).read_text(encoding="utf-8"))
    service = config["service"]
    service_url = f"http://{service['host']}:{service['port']}"
    timeout = service["timeout_seconds"] if args.timeout is None else args.timeout
    payload = {
        "prompt": args.prompt,
        "max_new_tokens": config["max_new_tokens"] if args.max_new_tokens is None else args.max_new_tokens,
    }
    record = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "service_url": service_url,
        "timeout_seconds": timeout if math.isfinite(timeout) else str(timeout),
        "request": payload,
    }
    try:
        result = request_answer(service_url, payload, timeout)
        record.update(success=True, **result)
        print("模型回答：", result["response"]["answer"])
        print("生成耗时：", result["response"]["generation_seconds"], "秒")
        print("新增 token：", result["response"]["generated_tokens"])
        print("HTTP 请求耗时：", result["request_seconds"], "秒")
        exit_code = 0
    except ModelClientError as error:
        record.update(success=False, error={
            "kind": error.kind, "message": str(error),
            "http_status": error.status_code, "detail": error.detail,
        })
        print("调用失败：", error, file=sys.stderr)
        if error.detail is not None:
            print("错误详情：", json.dumps(error.detail, ensure_ascii=False), file=sys.stderr)
        exit_code = 1

    output_path = (PROJECT_ROOT / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("调用记录：", output_path)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
