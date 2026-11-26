"""
T08 本机三路线联调入口。路由和参数固定使用原始 Qwen 服务。

负责读取配置、创建检索器与会话、注入模型客户端、执行一轮图并落盘。
不启动 T02 服务，不加载生成模型权重；本地分词器只用于回答前的长度预算。
"""

import argparse
from datetime import datetime, timezone
import json

from src.context import SessionStore
from src.graph import build_graph, invoke_session
from src.model.model_client import request_answer, ModelClientError
from src.retrieval import PROJECT_ROOT, NoteRetriever


def main() -> int:
    """
    执行单题三路线图并保存原始模型请求和图轨迹。

    Args:
        无。问题从必填命令行参数 --question 读取。

    Returns:
        int: 图成功为 0，澄清或失败为 1。
    """
    # 使用模块说明作为命令行帮助；不提供问题时 argparse 会直接报错退出。
    parser = argparse.ArgumentParser(description=__doc__.strip())
    parser.add_argument("--question", required=True, action="append", help="按顺序重复传入同一会话的多轮输入")
    args = parser.parse_args()
    # 模型配置提供服务地址和生成设置，检索配置用于初始化已有说明检索器。
    config = json.loads((PROJECT_ROOT / "configs/model.json").read_text(encoding="utf-8"))
    retrieval = json.loads((PROJECT_ROOT / "configs/retrieval.json").read_text(encoding="utf-8"))
    service = config["service"]
    url = f"http://{service['host']}:{service['port']}"
    calls = []  # 按调用顺序收集路由及最终回答的实际提示和响应。

    def generate(prompt: str) -> dict:
        """
        调用原始模型并记录请求，检查实际模型身份。
        发请求、留记录、检查身份

        Args:
            prompt (str): 路由或最终回答提示。

        Returns:
            dict: 完整客户端结果。
        """
        # 先追加请求再发 HTTP；若超时或连接失败，该条仍保留已发送的提示。
        # 本闭包通过 append 修改外层列表，无需 nonlocal（没有重新绑定 calls）。
        entry = {"prompt": prompt}
        calls.append(entry)
        result = request_answer(url, {"prompt": prompt, "max_new_tokens": config["max_new_tokens"]},
                                service["timeout_seconds"])
        # entry 已在 calls 中，追加结果会同步反映到同一条记录。
        entry["result"] = result
        expected = ("model_id", "revision", "enable_thinking", "max_new_tokens")
        # 核对服务报告的标识和设置；不等于重新校验模型权重文件。
        if any(result["response"].get(key) != config[key] for key in expected):
            raise ModelClientError("settings_mismatch", "原始模型服务身份或生成设置不一致。")
        return result

    from transformers import AutoConfig, AutoTokenizer
    from src.model.model_inference import encode_chat
    # 只读本地分词器与配置，和 T02 复用 encode_chat，统一模板后 token 计数。
    path = (PROJECT_ROOT / config["model_path"]).resolve()
    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
    limit = AutoConfig.from_pretrained(path, local_files_only=True).max_position_embeddings
    # 三元组：完整提示的计数函数、模型上下文上限、为回答预留的输出 token。
    # 当前图将预算用于最终回答；路由提示并未在此单独进行 token 裁剪。
    budget = (lambda prompt: encode_chat(tokenizer, prompt, config["enable_thinking"])[2]["input_ids"].shape[1],
              limit, config["max_new_tokens"])
    # 每次运行新建空会话；没有跨命令持久化，也不会自动续接上一次问题。
    store = SessionStore()
    # router 和 generate 目前注入同一个客户端：先判断路线，再生成回答。
    # 提供 router 才启用三路线；NoteRetriever.search 仅在经过 retrieval 时调用。
    graph = build_graph(NoteRetriever(retrieval).search, generate, router=generate, budget=budget)
    sid = store.create().session_id
    turns = []
    for question in args.question:
        # 同一条命令的所有问题复用 sid；此轮调用记录从当前列表末尾开始截取。
        start = len(calls)
        turn = invoke_session(graph, store, sid, question)
        turns.append({**turn, "model_calls": calls[start:]})
    # 单题沿用原 JSON 结构，多轮增加 turns，保留每轮原始输入输出与独立调用记录。
    result = turns[0] if len(turns) == 1 else {
        "session_id": sid, "status": turns[-1]["status"], "turns": turns,
    }
    # UTC 时间区分各轮；x 模式独占创建，同名文件存在时明确报错而不覆盖。
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = PROJECT_ROOT / "results/T08" / f"graph_{run_id}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(f"运行记录：{output}")
    # 优先显示最终回答；没有回答时显示澄清文字，否则显示结构化错误。
    for turn in turns:
        print(f"输入：{turn.get('user_input', turn['question'])}")
        print(turn.get("response", {}).get("response", {}).get("answer",
              turn.get("message", turn.get("error"))))
    # 澄清也返回 1：表示当前问题尚未完成回答，不代表一定发生服务故障。
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
