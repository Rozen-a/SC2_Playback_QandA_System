"""
T02：将本地模型推理包装为仅供本机调用的 HTTP 服务。

职责：
- 启动服务
- 校验请求
- 调用推理函数
- 返回结果
"""

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
    """只接收问题和可选的长度上限，其他生成设置沿用模型配置。"""

    model_config = ConfigDict(extra="forbid")  # 禁止接收未定义的字段
    prompt: str = Field(strict=True, min_length=1, max_length=4000)
    max_new_tokens: int | None = Field(default=None, strict=True, ge=1, le=512)

    @field_validator("prompt")
    @classmethod
    def reject_blank_prompt(cls, value: str) -> str:
        """
        自定义检查方法，通过校验器确保 prompt 不为空白字符
        - cls: 代表当前类
        - value: 要验证的字段值
        """
        if not value.strip():
            raise ValueError("问题不能只包含空白字符。")
        return value


@asynccontextmanager
async def lifespan(app: FastAPI):
    """在接收请求前加载一次模型；模型加载失败时让服务启动失败。"""
    config = json.loads((PROJECT_ROOT / "configs/model.json").read_text(encoding="utf-8"))
    logger.info("Loading model: %s; revision: %s", config["model_id"], config["revision"])
    started = time.perf_counter()
    tokenizer, model = load_local_model(config)
    torch.cuda.synchronize()

    # 把模型和配置保存在 app.state 中
    app.state.config = config
    app.state.tokenizer = tokenizer
    app.state.model = model
    # 请求在工作线程中执行；锁用于防止多次生成同时占用 GPU。
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

# 创建 FastAPI 应用
app = FastAPI(title="SC2 本地模型服务", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    """返回实际模型设备与加载信息；不执行生成。"""
    return app.state.health


@app.post("/generate")
def generate(request: GenerateRequest):
    """校验请求后调用真实模型；每次请求使用独立配置，避免改写默认值。"""
    if not app.state.generation_lock.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="模型正在生成回答，请稍后重试。")
    try:
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
    config = json.loads((PROJECT_ROOT / "configs/model.json").read_text(encoding="utf-8"))
    service = config["service"]
    if service["host"] != "127.0.0.1":
        raise ValueError("当前服务仅支持本机地址 127.0.0.1。")
    # 使用一个进程，避免多个工作进程各自加载模型；关闭热重载。
    uvicorn.run(app, host=service["host"], port=service["port"], workers=1, reload=False)


if __name__ == "__main__":
    main()
