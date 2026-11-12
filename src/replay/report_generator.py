"""
将回放解析的检查结果与导出记录写成 Markdown 报告。
"""

from pathlib import Path

from stats_validation import STAT_FIELDS


def write_t01_report(
    *,
    info: dict,
    sample_rows: list[dict],
    stats_event_count: int,
    output_dir: Path,
    report_filename: str = "data_check.md",
    manual_review_link: str | None = "manual_review.md",
) -> Path:
    """
    将调用方提供的比赛摘要、字段检查结果和导出记录写成报告。

    Args:
        - info (dict): 回放来源、解析版本、共同采样点、冲突和字段状态摘要。
        - sample_rows (list[dict]): 已整理的样本行，含玩家、时间、统计值及各字段状态。
        - stats_event_count (int): 回放中参与统计检查的事件总数。
        - output_dir (Path): 调用方已创建的报告输出目录。
        - report_filename (str): 报告文件名。
        - manual_review_link (str | None): 已有人工复核记录的相对链接，None 表示没有可引用的记录。

    Returns:
        - report_path (Path): 生成的 Markdown 报告路径。
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

    # 共同点总数表示可导出的时点，表格标题另写本次实际选中的时点和统计行数。
    report = [
        f"# 回放 {replay_id} 数据检查记录", "",
        "本文件汇总解析结果、字段一致性检查与导出范围。", "",
        f"- 文件：{source_file}",
        f"- SHA-256：{replay_sha256}",
        f"- 游戏版本：{game_version}；解析器版本：{parser_version}",
        f"- 统计事件：{stats_event_count} 条；排除冲突后共同采样点：{common_frame_count} 个。",
        f"- 冲突组合：{conflict_count} 个。",
        f"- 全部事件三字段的检查状态计数：{dict(quality_counts)}", "",
        f"## 导出记录（{len(info['selected_frames'])} 个采样点，{len(sample_rows)} 条记录）", "",
        "| 时间编号 | 玩家编号 | 玩家 | 矿 | 气 | 活跃工人数 | Tracker 序号（从 0 开始） | 三字段状态 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    # 每条统计记录占一行。用“空”标记不可用字段，便于与有效的零值区分。
    for row in sample_rows:
        values = ["空" if row[field] is None else str(row[field]) for field in STAT_FIELDS]
        statuses = ", ".join(row[field + "_status"] for field in STAT_FIELDS)
        report.append(
            f"| {row['game_loop']} | {row['pid']} | {row['player_name']} | "
            + " | ".join(values) + f" | {row['tracker_index']} | {statuses} |"
        )
    # 有人工复核材料时才显示链接。回放 A 的既有复核只覆盖前三个时点。
    report += [
        "", "## 重复记录", "",
        *[f"- 玩家 {item['pid']}，时间编号 {item['game_loop']}，事件序号 {item['tracker_indices']}，冲突：{item['conflict']}。"
          for item in info["duplicate_groups"]],
    ]
    if manual_review_link is not None:
        report += [
            "", "## 人工复核记录", "",
            f"回放 A 前三个共同采样点的人工核对见 [manual_review.md]({manual_review_link})。",
        ]
    report += ["", "共同采样点数量不代表每个字段均可用。", ""]
    # 用换行符连接各行，以 UTF-8 写入；返回路径供调用方显示。
    report_path = output_dir / report_filename
    report_path.write_text("\n".join(report), encoding="utf-8")
    return report_path
