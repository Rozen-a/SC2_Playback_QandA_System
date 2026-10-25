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
    """生成自动检查报告，并返回文件路径。

    info 是比赛与质量检查摘要，sample_rows 是带字段状态的样本记录。
    调用方负责提前完成校验；本函数只组织文字和表格，不修改输入数据。
    output_dir 是调用方已创建的报告目录，文件名固定为 data_check.md。
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

    # 先组织报告内容；无效字段显示“空”，不将其替换为零。
    report = [
        f"# 回放 {replay_id} 的 T01 自动检查记录", "",
        "本文件由解析程序生成。已执行自动字段一致性检查，尚未完成独立人工复核。", "",
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
    # 追加重复事件摘要、人工复核步骤及当前回放的文件替换说明。
    report += [
        "", "## 重复记录", "",
        *[f"- 玩家 {item['pid']}，时间编号 {item['game_loop']}，事件序号 {item['tracker_indices']}，冲突：{item['conflict']}。"
          for item in info["duplicate_groups"]],
        "", "## 人工复核步骤", "",
        f"1. 打开 data/decoded/{replay_id}_tracker_stats.json，按表中 tracker_index 找到六条事件。",
        "2. 检查 pid、game_loop 和玩家对应关系。",
        '3. JSON 中 raw_stats 的键为字符串；逐项查看 "0"、"1"、"4" 对应的值，与 CSV 的矿、气、活跃工人数比较。',
        "4. 查看 field_checks：缺失、负数或改写值不能作为已确认真实值。",
        "5. 在独立的 manual_review.md 中记录复核人、实际日期、逐条结果及问题；不要修改本自动报告伪称已人工通过。",
        "", "## 文件替换情况", "",
        "用户已说明先前文件错误，后用新文件替换且文件名未变。",
        "聊天中早先记录的校验值：63BA4A0FA2C8B7DAB7630283C290973D32515DB7027C2C871A221E52CE42A2F7。",
        f"本次实际读取的校验值：{replay_sha256}。实际替换日期尚待用户补充，不能从文件时间推断。",
        "", "共同采样点数量不代表每个字段均可用；程序运行成功不代表兼容所有回放。", "",
    ]
    # 用换行符连接各行，以 UTF-8 写入；返回路径供调用方显示。
    report_path = output_dir / "data_check.md"
    report_path.write_text("\n".join(report), encoding="utf-8")
    return report_path
