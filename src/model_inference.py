"""T02：从本地加载固定版本的模型，完成直接推理并保存实际运行记录。"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import torch
import transformers
from transformers import AutoModelForCausalLM, AutoTokenizer, set_seed


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_local_model(config: dict):
    """只读取本地模型文件；显卡不可用时明确报错，便于发现环境问题。"""
    model_path = (PROJECT_ROOT / config["model_path"]).resolve()
    if not model_path.is_dir():
        raise FileNotFoundError(f"模型目录不存在：{model_path}")
    if config["device"] != "cuda" or not torch.cuda.is_available():
        raise RuntimeError("当前配置需要可用的 CUDA 显卡，请检查 PyTorch 和驱动。")
    if config["dtype"] != "float16":
        raise ValueError("当前加载程序支持的 dtype 为 float16。")

    print(f"加载本地模型：{model_path}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    # 显式指定精度，再将权重放到显卡；无需自动分配设备所需的额外依赖。
    model = AutoModelForCausalLM.from_pretrained(
        model_path, dtype=torch.float16, local_files_only=True
    ).to(config["device"])
    model.eval()
    return tokenizer, model


def generate_answer(tokenizer, model, prompt: str, config: dict) -> dict:
    """沿用模型提供的对话模板，返回实际生成文本、长度及耗时。"""
    if not prompt.strip():
        raise ValueError("问题不能为空。")
    if type(config["max_new_tokens"]) is not int or not 1 <= config["max_new_tokens"] <= 512:
        raise ValueError("max_new_tokens 必须为 1～512 之间的整数。")

    set_seed(config["seed"])
    messages = [{"role": "user", "content": prompt}]
    # 固定关闭思考模式，后续推理和训练需沿用相同的模板与设置。
    rendered_prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=config["enable_thinking"],
    )
    inputs = tokenizer(rendered_prompt, return_tensors="pt", add_special_tokens=False)
    inputs = inputs.to(model.device)
    input_tokens = inputs["input_ids"].shape[1]

    # CUDA 异步执行；前后同步后再计时，记录本次生成所耗时间。
    torch.cuda.synchronize()
    started = time.perf_counter()
    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=config["max_new_tokens"],
            do_sample=config["do_sample"],
            temperature=config["temperature"],
            top_p=config["top_p"],
            top_k=config["top_k"],
            min_p=config["min_p"],
        )
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - started

    # generate 返回“输入＋新增内容”，只解码新增部分，避免把问题当成回答。
    new_ids = output[0, input_tokens:]
    eos_ids = model.generation_config.eos_token_id
    eos_ids = eos_ids if isinstance(eos_ids, list) else [eos_ids]
    return {
        "messages": messages,
        "rendered_prompt": rendered_prompt,
        "answer": tokenizer.decode(new_ids, skip_special_tokens=True).strip(),
        "input_tokens": input_tokens,
        "generated_tokens": len(new_ids),
        "stopped_on_eos": bool(len(new_ids) and new_ids[-1].item() in eos_ids),
        "generation_seconds": round(elapsed, 3),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/model.json")
    parser.add_argument("--prompt", default="请用一句简短的中文介绍你自己。")
    parser.add_argument("--max-new-tokens", type=int)
    parser.add_argument("--output", default="results/T02/direct_inference.json")
    args = parser.parse_args()

    config_path = (PROJECT_ROOT / args.config).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if args.max_new_tokens is not None:
        config["max_new_tokens"] = args.max_new_tokens

    started = time.perf_counter()
    tokenizer, model = load_local_model(config)
    torch.cuda.synchronize()
    load_seconds = time.perf_counter() - started
    result = generate_answer(tokenizer, model, args.prompt, config)

    record = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": config,
        "resolved_model_path": str((PROJECT_ROOT / config["model_path"]).resolve()),
        "torch_version": torch.__version__,
        "transformers_version": transformers.__version__,
        "cuda_version": torch.version.cuda,
        "gpu_name": torch.cuda.get_device_name(),
        "model_load_seconds": round(load_seconds, 3),
        **result,
    }
    output_path = (PROJECT_ROOT / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("模型回答：", result["answer"], flush=True)
    print(f"生成耗时：{result['generation_seconds']} 秒；新增 token：{result['generated_tokens']}")
    print(f"运行记录：{output_path}")


if __name__ == "__main__":
    main()
