"""T02 本地模型推理，提供模型加载、回答生成和命令行记录功能。"""

import argparse  # 用于读取命令行参数
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import torch
import transformers
from transformers import AutoModelForCausalLM, AutoTokenizer, set_seed


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_local_model(config: dict):
    """从本地目录加载分词器和模型，将模型放到 CUDA 设备并设为评估模式。

    Args:
        - config (dict): 模型配置。model_path 指定模型目录，相对路径以仓库根目录为基准。
          device 和 dtype 分别指定运行设备和精度，当前要求 cuda 和 float16。

    Returns:
        - (tokenizer, model) (tuple): 分词器和已在 CUDA 上进入评估模式的生成模型。
    """
    model_path = (PROJECT_ROOT / config["model_path"]).resolve()
    if not model_path.is_dir():
        raise FileNotFoundError(f"模型目录不存在：{model_path}")
    if config["device"] != "cuda" or not torch.cuda.is_available():
        raise RuntimeError("当前配置需要可用的 CUDA 显卡，请检查 PyTorch 和驱动。")
    if config["dtype"] != "float16":
        raise ValueError("当前加载程序支持的 dtype 为 float16。")
    
    # 只读本地模型文件，保证推理使用已下载的版本。
    print(f"加载本地模型：{model_path}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    # 显式指定精度，再将权重放到显卡；无需自动分配设备所需的额外依赖。
    model = AutoModelForCausalLM.from_pretrained(
        model_path, dtype=torch.float16, local_files_only=True
    ).to(config["device"])
    model.eval()  # 切换为评估模式，使模型中的相关层按推理时的方式工作
    return tokenizer, model


def generate_answer(tokenizer, model, prompt: str, config: dict) -> dict:
    """按模型对话模板生成回答，并记录新增 token 数和生成耗时。

    Args:
        - tokenizer (PreTrainedTokenizerBase): 与模型匹配的分词器，负责模板渲染和编解码。
        - model (PreTrainedModel): 已加载到 CUDA 设备的生成模型。
        - prompt (str): 用户问题，内容不能全为空白。
        - config (dict): 生成设置，包括随机种子、思考模式、输出上限及采样参数。
          max_new_tokens 必须是 1 至 512 的整数。

    Returns:
        - result (dict): 包含输入消息、渲染后的提示、回答、输入和新增 token 数、
          是否遇到结束标记，以及以秒为单位的生成耗时。
    """
    # strip() 去掉字符串首尾的空白字符后判断是否为空
    if not prompt.strip(): 
        raise ValueError("问题不能为空。")
    # 限制新增输出 token 的数量，避免生成过长的回答
    if type(config["max_new_tokens"]) is not int or not 1 <= config["max_new_tokens"] <= 512:
        raise ValueError("max_new_tokens 必须为 1～512 之间的整数。")

    set_seed(config["seed"])
    messages = [{"role": "user", "content": prompt}]
    # 思考模式由配置决定。对比实验应记录并统一这个设置。
    rendered_prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=config["enable_thinking"],
    )
    inputs = tokenizer(
        rendered_prompt, 
        return_tensors="pt",  # 返回 PyTorch 张量
        add_special_tokens=False
        )
    inputs = inputs.to(model.device)
    # 计算输入的 token 数量
    input_tokens = inputs["input_ids"].shape[1]  # [输入条数, 每条输入的 token 数]

    # 生成前后同步 CUDA，避免异步执行造成计时偏差。
    torch.cuda.synchronize()  # 确保前面的操作完成后再开始计时
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
    torch.cuda.synchronize()  # 确保生成完成后再计时
    elapsed = time.perf_counter() - started

    # generate 返回“输入＋新增内容”，只解码新增部分，避免把问题当成回答。
    new_ids = output[0, input_tokens:]
    # EOS 表示序列结束标记
    eos_ids = model.generation_config.eos_token_id
    # 模型配置可能指定一个或多个 EOS 编号，统一按列表检查最后一个新增 token。
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
    """读取命令行参数，执行一次本地推理并将环境信息和回答写入 JSON。"""
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
