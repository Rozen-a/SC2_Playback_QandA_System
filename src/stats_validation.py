"""检查三项目标字段，避免把缺失、异常或解析器改写值当作真实值。"""


# 定义原始统计字典中各字段的位置
STAT_FIELDS = {
    "minerals_current": 0, # 矿
    "vespene_current": 1, # 气
    "workers_active_count": 4, # 活跃工人数
}


def check_stat(raw_value, parsed_value):
    """
    比较原始值和 sc2reader 处理后的值
    返回原始值、解析值、可用值和检查状态；
    不可用值保留为 None
    """
    if raw_value is None: # 原始值缺失
        status = "missing"
    elif type(raw_value) is not int or raw_value < 0:
        status = "invalid_raw" # 原始值为负数或不是整数
    elif parsed_value != raw_value:
        status = "parser_mismatch" # 原始值有效，但解析后的值不同
    else:
        status = "raw_matches_parser" # 原始值为非负整数，且与解析值一致

    return {
        "raw": raw_value, # 原始值，可能缺失或无效
        "parsed": parsed_value, # 解析器处理后的值
        "value": raw_value if status == "raw_matches_parser" else None, # 可用值，只有原始值有效且与解析值一致时才使用原始值
        "status": status, # 检查状态
        "parser_changed": raw_value != parsed_value, # 解析器是否改写了原始值
    }
