"""
T05 说明问答。先展示检索结果，再使用 T03 模板调用 T02 模型服务。
"""

import argparse
from collections.abc import Callable
from datetime import datetime, timezone
import json
import re

from src.model.model_client import ModelClientError, request_answer
from src.retrieval import PROJECT_ROOT, NoteRetriever, display_matches


PLACEHOLDER = re.compile(r"\{(question|evidence)\}")


def build_answer_prompt(question: str, matches: list[dict]) -> str:
    """
    将当前问题和说明证据填入 T03 回答模板，并附加检索规则。

    Args:
        - question (str): 用户原始问题。
        - matches (list[dict]): 检索到的候选说明，含正文、出处和相似度。

    Returns:
        - prompt (str): 发给 T02 模型服务的完整回答提示。
    """
    prompt_dir = PROJECT_ROOT / "prompts"
    template = (prompt_dir / "answer.txt").read_text(encoding="utf-8")
    rules = (prompt_dir / "retrieval_rules.txt").read_text(encoding="utf-8")
    if PLACEHOLDER.findall(template) != ["question", "evidence"]:
        raise ValueError("T03 回答模板必须依次包含 question 和 evidence 占位符，各一次。")

    # 分数用于检索排名和人工核对。回答模型根据正文判断证据是否足够。
    passages = [{key: match[key] for key in ("id", "title", "text", "source")} for match in matches]
    values = {
        "question": question,
        "evidence": json.dumps({"notes": passages}, ensure_ascii=False),
    }
    # 把说明规则放在示例之后，紧贴当前题。原有统计示例继续使用 Tracker 序号。
    current_question = "\n问题\n{question}"
    if current_question not in template:
        raise ValueError("T03 回答模板缺少当前问题段。")
    template = template.replace(current_question, "\n" + rules.rstrip() + "\n" + current_question, 1)
    # 仅替换命名占位符，保留 T03 示例中的 JSON 大括号。
    return PLACEHOLDER.sub(lambda match: values[match[1]], template)


def format_citations(answer: str, matches: list[dict]) -> tuple[str, list[str]]:
    """
    根据本题候选资料补全出处，并检查来源行的格式和编号。

    Args:
        - answer (str): 模型生成的原始回答。
        - matches (list[dict]): 本题实际检索到的候选片段。

    Returns:
        - result (tuple[str, list[str]]): 展示文本和引用问题列表。
    """
    lines = [line.strip() for line in answer.splitlines() if line.strip()]
    if len(lines) != 2 or not lines[0].startswith("答案：") or not lines[1].startswith("来源："):
        return answer, ["回答应包含答案和来源两行。"]
    citation = lines[1].removeprefix("来源：").strip().rstrip("。")
    if citation == "无相关资料":
        return answer, []

    # 只接受本题候选片段里的编号。出处来自资料库，相关性仍需结合正文核对。
    ids = re.split(r"[、，,\s]+", citation)
    sources = {match["id"]: match["source"] for match in matches}
    if any(note_id not in sources for note_id in ids):
        return answer, ["来源行应只包含本题候选片段的编号，或填写无相关资料。"]
    references = [
        f"{note_id}（{sources[note_id]['path']} · {sources[note_id]['section']}）"
        for note_id in dict.fromkeys(ids)
    ]
    return lines[0] + "\n来源：" + "；".join(references), []


def answer_question(question: str, retriever: NoteRetriever, generate: Callable[[str], dict]) -> dict:
    """
    检索并展示说明片段，然后生成回答或记录模型服务错误。

    Args:
        - question (str): 用户原始问题。
        - retriever (NoteRetriever): 已加载向量模型和索引的检索器。
        - generate (Callable[[str], dict]): 接收提示并返回 T02 客户端结果的函数。

    Returns:
        - record (dict): 问题、候选片段、实际提示、原始响应、展示答案与引用问题，或服务错误。
    """
    matches = retriever.search(question)
    # 先将候选片段输出到终端，再发送生成请求，便于独立检查检索效果。
    display_matches(question, matches)
    prompt = build_answer_prompt(question, matches)
    record = {"question": question, "matches": matches, "prompt": prompt}
    try:
        result = generate(prompt)
    except ModelClientError as error:
        record.update(status="model_error", error={
            "kind": error.kind, "message": str(error),
            "http_status": error.status_code, "detail": error.detail,
        })
        print(f"回答失败：{error}", flush=True)
    else:
        # 保留原始响应供复测对照，另存补全出处后的展示文本。
        display_answer, citation_issues = format_citations(result["response"]["answer"], matches)
        record.update(status="ok", display_answer=display_answer, citation_issues=citation_issues, **result)
        print(display_answer, flush=True)
        for issue in citation_issues:
            print(f"引用待核对：{issue}", flush=True)
    return record


def main() -> int:
    """
    读取命令行问题，运行说明问答并保存检索与生成记录。

    Returns:
        - exit_code (int): 全部回答生成成功为 0，读取或运行失败为 1。
    """
    parser = argparse.ArgumentParser(description=__doc__.strip())
    parser.add_argument("--query", action="append", required=True, help="可重复传入多个说明问题")
    args = parser.parse_args()
    try:
        config_dir = PROJECT_ROOT / "configs"
        retrieval_config = json.loads((config_dir / "retrieval.json").read_text(encoding="utf-8"))
        model_config = json.loads((config_dir / "model.json").read_text(encoding="utf-8"))
        retriever = NoteRetriever(retrieval_config)
        service = model_config["service"]
        service_url = f"http://{service['host']}:{service['port']}"
        expected = {key: model_config[key] for key in ("model_id", "revision", "enable_thinking", "max_new_tokens")}

        def generate(prompt: str) -> dict:
            """
            通过 T02 客户端发送问题并核对返回的模型设置。

            Args:
                - prompt (str): 含说明证据的完整提示。

            Returns:
                - result (dict): HTTP 状态、请求耗时及模型原始响应。
            """
            payload = {"prompt": prompt, "max_new_tokens": expected["max_new_tokens"]}
            result = request_answer(service_url, payload, service["timeout_seconds"])
            if any(result["response"].get(key) != value for key, value in expected.items()):
                raise ModelClientError("settings_mismatch", "模型服务返回的设置与本地配置不一致。")
            return result

        results = [answer_question(question, retriever, generate) for question in args.query]
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output = PROJECT_ROOT / "results" / "T05" / f"rag_qa_{run_id}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as stream:
            json.dump({
                "retrieval_config": retrieval_config,
                "model_settings": expected,
                "service_url": service_url,
                "results": results,
            }, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except (OSError, ValueError, KeyError, ImportError) as error:
        print(f"说明问答失败：{error}")
        return 1

    print(f"\n运行记录：{output}")
    return 0 if all(result["status"] == "ok" for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
