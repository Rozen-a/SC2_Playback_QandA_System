"""
T03 批量调用 T02 服务，保存三版对比或选定模板复核的运行记录。
"""

import argparse
import json
from datetime import datetime, timezone
import re

from src.model.model_client import PROJECT_ROOT, ModelClientError, request_answer


PROMPT_NAMES = ("direct", "rules", "examples")
PLACEHOLDER = re.compile(r"\{(question|evidence)\}")  # 匹配占位符，按顺序替换 question 和 evidence
# re.compile() 将正则表达式编译成一个可复用的对象，后面用它做两件事：检查占位符和替换占位符


def prepare_requests(holdout: bool = False) -> list[dict]:
    """
    将开发题或复核题填入对应模板，并在调用前检查输入长度。

    Args:
        - holdout (bool): 为 True 时用选定模板回答复核题。

    Returns:
        - requests (list[dict]): 按题目和提示版本排序的请求记录。
    """
    prompt_names = ("answer",) if holdout else PROMPT_NAMES
    dataset = "holdout_A.jsonl" if holdout else "dev_A.jsonl"
    # 模板名作为键、模板全文作为值
    templates = {
        name: (PROJECT_ROOT / "prompts" / f"{name}.txt").read_text(encoding="utf-8")
        for name in prompt_names
    }
    # 检查每个模板是否包含 question 和 evidence 占位符，且各一次，且{question} 出现在 {evidence} 前面
    for name, template in templates.items():
        if PLACEHOLDER.findall(template) != ["question", "evidence"]:
            raise ValueError(f"{name}.txt 必须依次包含 question 和 evidence 占位符，各一次。")

    requests = []
    questions = (PROJECT_ROOT / "eval" / dataset).read_text(encoding="utf-8")
    for line in questions.splitlines():
        question = json.loads(line)  # `json.loads()` 是从 JSON 文本读成 Python 对象，`json.dumps()` 是把 Python 对象写成 JSON 文本
        # 单次替换保留示例里的 JSON 大括号，也避免把评分字段传给模型。
        values = {
            "question": question["question"],
            "evidence": json.dumps(question["evidence"], ensure_ascii=False),  # ensure_ascii=False: 让中文直接保留为中文
        }
        # 把数据填入每个模板
        for name, template in templates.items():
            prompt = PLACEHOLDER.sub(lambda match: values[match[1]], template)
                # sub() 是 Python 正则表达式的替换方法：在原字符串里找到符合规则的内容，把匹配到的整段文字换掉，并返回一个新字符串。
                # PLACEHOLDER.sub(..., template) 在 template 中寻找匹配项。每找到一项，就把匹配对象传给 lambda 函数
            if len(prompt.strip()) > 4000:
                raise ValueError(f"{question['id']}/{name} 超过服务的 4000 字符限制。")
            requests.append({"question_id": question["id"], "variant": name, "prompt": prompt})
    if not requests:
        raise ValueError(f"{dataset} 题集为空。")
    return requests


def main() -> int:
    """
    逐条发送请求，及时保存回答或错误。

    Returns:
        - exit_code (int): 全部成功为 0，输入无效或调用失败为 1。
    """
    parser = argparse.ArgumentParser(description=__doc__.strip())
    parser.add_argument("--holdout", action="store_true", help="用选定模板回答回放 A 的复核题")
    args = parser.parse_args()
    # 先准备整批请求，再读模型配置
    try:
        pending = prepare_requests(holdout=args.holdout)
        config = json.loads((PROJECT_ROOT / "configs" / "model.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError) as error:
        print(f"无法准备对比请求：{error}")
        return 1

    # 读取模型服务配置，构造请求参数和输出文件路径
    service = config["service"]
    service_url = f"http://{service['host']}:{service['port']}"
    expected = {key: config[key] for key in ("model_id", "revision", "enable_thinking", "max_new_tokens")}
    config_keys = ("do_sample", "temperature", "top_p", "top_k", "min_p", "seed")
    settings = {**expected, **{key: config[key] for key in config_keys}}
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")   #用 UTC 时间生成文件名标识
    file_prefix = "holdout_answers" if args.holdout else "answers"
    output = PROJECT_ROOT / "results" / "T03" / f"{file_prefix}_{run_id}.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    print(f"输出文件：{output}", flush=True)

    # 每次运行使用新文件，每收到一次响应就写入一行，保留已完成的请求。
    # "x" 只允许创建新文件，如果同名文件已存在，会报错，不会覆盖。
    with output.open("x", encoding="utf-8") as stream:
        for index, item in enumerate(pending, start=1):
            payload = {"prompt": item["prompt"], "max_new_tokens": expected["max_new_tokens"]}  # 发送给模型服务
            record = {**item, "service_url": service_url, "config_settings": settings}  # 本地保存和追查
            try:
                result = request_answer(service_url, payload, service["timeout_seconds"])
                response = result["response"]
                record.update(result)
                mismatches = [key for key, value in expected.items() if response.get(key) != value]  # 收集所有不一致的字段名
                if mismatches:
                    raise ModelClientError("settings_mismatch", f"服务响应与配置不一致：{', '.join(mismatches)}")
                # 检查是否达到最大 token 限制，且没有在 EOS 停止
                record["hit_token_limit"] = (
                    response["generated_tokens"] == expected["max_new_tokens"]
                    and response.get("stopped_on_eos") is False
                )
                record["status"] = "ok"
            except ModelClientError as error:
                record.update(status="error", error={
                    "kind": error.kind, "message": str(error),
                    "http_status": error.status_code, "detail": error.detail,
                })

            stream.write(json.dumps(record, ensure_ascii=False) + "\n")  # 每条记录转成一行 JSON，再加换行
            stream.flush()  # 将当前的文件缓冲写出，使后面的请求失败时，先前已写出的结果仍可查看。
            label = f"[{index}/{len(pending)}] {item['question_id']}/{item['variant']}"
            if record["status"] == "error":
                print(f"{label} 失败：{record['error']['message']}", flush=True)
                return 1
            print(f"{label} 完成", flush=True)

    print(f"已保存 {len(pending)} 条模型回答。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
