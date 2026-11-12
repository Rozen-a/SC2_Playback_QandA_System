"""
T05 说明检索。加载本地向量模型和索引，返回相关片段、分数及来源。
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_notes(config: dict) -> tuple[list[dict], str]:
    """
    读取说明条目及原文件校验值，检查索引所需的编号。

    Args:
        - config (dict): 检索配置，包含 notes_path。

    Returns:
        - data (tuple[list[dict], str]): 按原顺序排列的说明条目及文件 SHA-256。
    """
    content = (PROJECT_ROOT / config["notes_path"]).read_bytes()
    notes = [json.loads(line) for line in content.decode("utf-8").splitlines() if line.strip()]
    ids = [note["id"] for note in notes]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("说明资料不能为空，且编号必须唯一。")
    return notes, hashlib.sha256(content).hexdigest()


def load_encoder(config: dict):
    """
    从本机目录加载配置指定的文本向量模型。

    Args:
        - config (dict): 包含 model_path 和 device 的检索配置。

    Returns:
        - encoder (SentenceTransformer): 用于编码资料和问题的模型。
    """
    path = (PROJECT_ROOT / config["model_path"]).resolve()
    if not (path / "modules.json").is_file() or not (path / "model.safetensors").is_file():
        raise FileNotFoundError(f"本地向量模型不完整，请按 README 下载：{path}")
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(str(path), device=config["device"], local_files_only=True)


def index_metadata(config: dict, notes_sha256: str) -> dict:
    """
    记录会影响资料向量的模型版本和资料内容。

    Args:
        - config (dict): 包含模型标识和提交版本的检索配置。
        - notes_sha256 (str): 本次资料文件的 SHA-256。

    Returns:
        - metadata (dict): 用于检查索引是否仍可使用的元数据。
    """
    return {
        "model_id": config["model_id"], "revision": config["revision"],
        "notes_sha256": notes_sha256, "document_format": "title-newline-text-v1",
    }


class NoteRetriever:
    """
    复用同一份模型和索引，为多个问题检索说明片段。
    """

    def __init__(self, config: dict):
        """
        加载索引并核对资料版本、编号顺序和向量形状。

        Args:
            - config (dict): 索引路径、向量模型和查询参数。
        """
        self.config = config
        self.notes, digest = load_notes(config)
        path = PROJECT_ROOT / config["index_path"]
        if not path.is_file():
            raise FileNotFoundError(f"缺少向量索引，请先运行 python -m src.build_index：{path}")
        # 每行向量与同位置的资料编号对应，资料变化后必须重建。
        with np.load(path, allow_pickle=False) as index:
            ids = index["ids"].tolist()
            metadata = json.loads(index["metadata"].item())
            self.vectors = index["vectors"]
        if metadata != index_metadata(config, digest) or ids != [note["id"] for note in self.notes]:
            raise ValueError("资料或向量模型版本已变更，请重新生成索引。")
        if self.vectors.ndim != 2 or self.vectors.shape[0] != len(ids) or not np.isfinite(self.vectors).all():
            raise ValueError("索引的向量矩阵无效，请重新生成索引。")
        self.encoder = load_encoder(config)

    def search(self, question: str) -> list[dict]:
        """
        编码问题，按余弦相似度返回排名靠前的说明。

        Args:
            - question (str): 非空的用户问题。

        Returns:
            - matches (list[dict]): 含编号、正文、来源和相似度的说明列表。
        """
        question = question.strip()
        if not question:
            raise ValueError("检索问题不能为空。")
        top_k = self.config["top_k"]
        if type(top_k) is not int or top_k < 1:
            raise ValueError("top_k 必须是正整数。")
        # BGE 的检索指令只加在问题前面。归一化向量的点积就是余弦相似度。
        vector = self.encoder.encode(
            self.config["query_prefix"] + question, normalize_embeddings=True, convert_to_numpy=True
        )
        if vector.shape != (self.vectors.shape[1],) or not np.isfinite(vector).all():
            raise ValueError("问题向量与索引不兼容，请检查模型版本并重建索引。")
        scores = self.vectors @ vector
        order = np.argsort(-scores, kind="stable")[:top_k]
        return [{**self.notes[i], "score": float(scores[i])} for i in order]


def main() -> int:
    """
    读取命令行问题，显示检索结果并保存核对记录。

    Returns:
        - exit_code (int): 成功为 0，资料、模型或索引错误为 1。
    """
    parser = argparse.ArgumentParser(description=__doc__.strip())
    parser.add_argument("--query", action="append", required=True, help="可重复传入多个检索问题")
    args = parser.parse_args()
    try:
        config = json.loads((PROJECT_ROOT / "configs/retrieval.json").read_text(encoding="utf-8"))
        retriever = NoteRetriever(config)
        results = [{"question": q, "matches": retriever.search(q)} for q in args.query]
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output = PROJECT_ROOT / "results" / "T05" / f"retrieval_{run_id}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as stream:
            json.dump({"config": config, "results": results}, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except (OSError, ValueError, KeyError, ImportError) as error:
        print(f"检索失败：{error}")
        return 1

    for result in results:
        print(f"\n问题：{result['question']}")
        for match in result["matches"]:
            source = match["source"]
            print(f"- {match['id']} {match['title']}，相似度 {match['score']:.4f}")
            print(f"  {match['text']}（{source['path']} · {source['section']}）")
    print(f"\n运行记录：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
