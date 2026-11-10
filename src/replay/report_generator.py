"""将 T01 已计算的检查结果写成 Markdown 报告，不负责解析回放或检查统计值。"""

from pathlib import Path

from stats_validation import STAT_FIELDS


def write_t01_report(
    *,
    info: dict,
    sample_rows: list[dict],
    stats_event_count: int,
    output_dir: Path,
) -> Path:
    """将调用方已核验的比赛摘要和样本写成 Markdown 报告。

    Args:
        - info (dict): 回放来源、解析版本、共同采样点、冲突和字段状态摘要。
        - sample_rows (list[dict]): 已整理的样本行，含玩家、时间、统计值及各字段状态。
        - stats_event_count (int): 回放中参与统计检查的事件总数。
        - output_dir (Path): 调用方已创建的报告输出目录。

    Returns:
        - report_path (Path): 生成的 data_check.md 文件路径。
    """
    # 将报告所需的摘要取出，避免依赖解析程序中的回放对象或全局变量。
    replay_id = info["replay_id"]
    source_file = info["source_file"]
    replay_sha256 = info["sha256"]
    game_version = info["game_version"]
    parser_version = info["parser_version"]
    common_frame_count = len(info["common_frames_after_conflict_filter"])
    conflict_count = len(info["conflict_keys"])
    quality_counts = info["field_status_counts_all_events"]

    # 报告用“空”标记无效字段，便于与有效的零值区分。
    report = [
        f"# 回放 {replay_id} 的 T01 数据检查记录", "",
        "本文件汇总解析与字段一致性检查结果。人工复核记录见同目录 manual_review.md。", "",
        f"- 文件：{source_file}",
        f"- SHA-256：{replay_sha256}",
        f"- 游戏版本：{game_version}；解析器版本：{parser_version}",
        f"- 统计事件：{stats_event_count} 条；排除冲突后共同采样点：{common_frame_count} 个。",
        f"- 冲突组合：{conflict_count} 个。",
        f"- 全部事件三字段的检查状态计数：{dict(quality_counts)}", "",
        "## 六条样本记录", "",
        "| 时间编号 | 玩家编号 | 玩家 | 矿 | 气 | 活跃工人数 | Tracker 序号（从 0 开始） | 三字段状态 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    # 将每条样本写成一行 Markdown 表格，同时展示三项字段的检查状态。
    for row in sample_rows:
        values = ["空" if row[field] is None else str(row[field]) for field in STAT_FIELDS]
        statuses = ", ".join(row[field + "_status"] for field in STAT_FIELDS)
        report.append(
            f"| {row['game_loop']} | {row['pid']} | {row['player_name']} | "
            + " | ".join(values) + f" | {row['tracker_index']} | {statuses} |"
        )
    # 人工复核记录单独保存，重新生成报告时不覆盖，也不预设复核状态。
    report += [
        "", "## 重复记录", "",
        *[f"- 玩家 {item['pid']}，时间编号 {item['game_loop']}，事件序号 {item['tracker_indices']}，冲突：{item['conflict']}。"
          for item in info["duplicate_groups"]],
        "", "## 人工复核记录", "",
        "核对方法、逐条结果与复核状态见 [manual_review.md](manual_review.md)。",
        "", "共同采样点数量不代表每个字段均可用；程序运行成功不代表兼容所有回放。", "",
    ]
    # 用换行符连接各行，以 UTF-8 写入；返回路径供调用方显示。
    report_path = output_dir / "data_check.md"
    report_path.write_text("\n".join(report), encoding="utf-8")
    return report_path
