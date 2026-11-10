"""T02 本机模型服务，负责模型生命周期、HTTP 请求校验和推理调度。"""

from contextlib import asynccontextmanager
import json
import logging
import os
from threading import Lock
import time

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
import torch
import uvicorn

from model_inference import PROJECT_ROOT, generate_answer, load_local_model


logger = logging.getLogger("uvicorn.error")


class GenerateRequest(BaseModel):
    """生成接口的请求结构，包含问题和可选的新增 token 上限。"""

    model_config = ConfigDict(extra="forbid")  # 禁止接收未定义的字段
    prompt: str = Field(strict=True, min_length=1, max_length=4000)
    max_new_tokens: int | None = Field(default=None, strict=True, ge=1, le=512)

    @field_validator("prompt")
    @classmethod
    def reject_blank_prompt(cls, value: str) -> str:
        """拒绝仅由空白字符组成的问题。

        Args:
            - value (str): 请求中的问题文本。

        Returns:
            - value (str): 通过校验的原始问题文本，保留首尾空白。
        """
        if not value.strip():
            raise ValueError("问题不能只包含空白字符。")
        return value


@asynccontextmanager
async def lifespan(app: FastAPI):
    """在服务启动时加载模型并设置共享状态，在正常退出时释放资源。

    Args:
        - app (FastAPI): 当前服务应用。模型、分词器、生成锁和健康信息存入 app.state。
    """
    config = json.loads((PROJECT_ROOT / "configs/model.json").read_text(encoding="utf-8"))
    logger.info("Loading model: %s; revision: %s", config["model_id"], config["revision"])
    started = time.perf_counter()
    tokenizer, model = load_local_model(config)
    torch.cuda.synchronize()

    # 把模型和配置保存在 app.state 中
    app.state.config = config
    app.state.tokenizer = tokenizer
    app.state.model = model
    # 请求在工作线程中执行，生成锁保证同一时刻只有一个请求使用模型生成。
    app.state.generation_lock = Lock()
    app.state.health = {
        "status": "ready",
        "model_id": config["model_id"],
        "revision": config["revision"],
        "device": str(next(model.parameters()).device),
        "dtype": str(next(model.parameters()).dtype),
        "gpu_name": torch.cuda.get_device_name(),
        "model_load_seconds": round(time.perf_counter() - started, 3),
        "process_id": os.getpid(),
    }
    logger.info("Model ready: %s", json.dumps(app.state.health, ensure_ascii=False))
    try:
        yield
    finally:
        # 正常退出时释放服务持有的模型引用和 CUDA 缓存。
        del app.state.model
        del app.state.tokenizer
        del model, tokenizer
        torch.cuda.empty_cache()
        logger.info("Model released.")

# 将模型的加载和释放绑定到 FastAPI 应用的生命周期。
app = FastAPI(title="SC2 本地模型服务", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    """读取服务启动时记录的模型状态。

    Returns:
        - state (dict): 模型标识、版本、实际设备和精度、显卡名称、
          加载耗时（秒）及服务进程编号。
    """
    return app.state.health


@app.post("/generate")
def generate(request: GenerateRequest):
    """处理已通过请求校验的问题，并调用已加载模型生成回答。

    Args:
        - request (GenerateRequest): 用户问题和可选的新增 token 上限。
          省略上限时沿用服务默认设置。

    Returns:
        - response (dict): 模型标识和版本、设备、实际生成设置、
          输入消息、回答、token 数、停止状态及生成耗时（秒）。
    """
    # 非阻塞获取生成锁。模型忙碌时立即返回 503，让客户端自行决定何时重试。
    if not app.state.generation_lock.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="模型正在生成回答，请稍后重试。")
    try:
        # 请求只修改配置副本，后续请求仍使用服务的默认值。
        config = app.state.config.copy()
        if request.max_new_tokens is not None:
            config["max_new_tokens"] = request.max_new_tokens
        result = generate_answer(app.state.tokenizer, app.state.model, request.prompt, config)
        logger.info(
            "Generated %s tokens in %s seconds", result["generated_tokens"], result["generation_seconds"]
        )
        return {
            "model_id": config["model_id"],
            "revision": config["revision"],
            "device": app.state.health["device"],
            "enable_thinking": config["enable_thinking"],
            "max_new_tokens": config["max_new_tokens"],
            **result,
        }
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        logger.exception("Model generation failed")
        raise HTTPException(status_code=500, detail="模型生成失败，请查看服务日志。") from error
    finally:
        app.state.generation_lock.release()


def main():
    """读取监听配置并启动单进程 Uvicorn 服务。"""
    config = json.loads((PROJECT_ROOT / "configs/model.json").read_text(encoding="utf-8"))
    service = config["service"]
    if service["host"] != "127.0.0.1":
        raise ValueError("当前服务仅支持本机地址 127.0.0.1。")
    # 单进程且关闭热重载，避免重复加载模型权重。
    uvicorn.run(app, host=service["host"], port=service["port"], workers=1, reload=False)


if __name__ == "__main__":
    main()
