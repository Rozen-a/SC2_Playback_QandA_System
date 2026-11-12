"""
T05 向量索引构建。编码说明条目并保存编号和可复核的索引元数据。
"""

import argparse
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np

from src.retrieval import PROJECT_ROOT, index_metadata, load_encoder, load_notes


def build_index(config: dict) -> tuple[Path, tuple[int, ...]]:
    """
    将标题和正文编码成归一化向量，保存与资料编号一一对应的索引。

    Args:
        - config (dict): 资料路径、模型路径、输出路径和模型版本。

    Returns:
        - result (tuple[Path, tuple[int, ...]]): 索引文件路径与向量矩阵形状。
    """
    notes, digest = load_notes(config)
    # 标题与正文一起参与检索，说明文本不添加查询指令。
    documents = [f"{note['title']}\n{note['text']}" for note in notes]
    encoder = load_encoder(config)
    vectors = encoder.encode(documents, normalize_embeddings=True, convert_to_numpy=True)
    if vectors.ndim != 2 or vectors.shape[0] != len(notes) or not np.isfinite(vectors).all():
        raise ValueError("向量模型返回了无效的资料向量。")

    path = PROJECT_ROOT / config["index_path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    # 完整写入临时索引后再替换目标，避免中断时破坏现有索引。
    with NamedTemporaryFile(dir=path.parent, suffix=".npz", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            np.savez_compressed(
                stream, vectors=vectors, ids=[note["id"] for note in notes],
                metadata=json.dumps(index_metadata(config, digest)),
            )
            stream.close()
            temporary.replace(path)
        finally:
            stream.close()
            temporary.unlink(missing_ok=True)
    return path, vectors.shape


def main() -> int:
    """
    按检索配置构建本地索引，显示向量数量与维度。

    Returns:
        - exit_code (int): 构建成功为 0，读取或编码失败为 1。
    """
    parser = argparse.ArgumentParser(description=__doc__.strip())
    parser.parse_args()
    try:
        config = json.loads((PROJECT_ROOT / "configs/retrieval.json").read_text(encoding="utf-8"))
        path, shape = build_index(config)
    except (OSError, ValueError, KeyError, ImportError) as error:
        print(f"构建索引失败：{error}")
        return 1
    print(f"已保存 {shape[0]} 条资料的向量，每条 {shape[1]} 维。")
    print(f"索引文件：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
