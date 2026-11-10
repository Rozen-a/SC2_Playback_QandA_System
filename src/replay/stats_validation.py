"""检查三项目标字段，避免把缺失、异常或解析器改写值当作真实值。"""


# 原始统计字典的整数键对应矿量、气量和活跃工人数。
STAT_FIELDS = {
    "minerals_current": 0, # 矿
    "vespene_current": 1, # 气
    "workers_active_count": 4, # 活跃工人数
}


def check_stat(raw_value, parsed_value):
    """比较原始统计值与 sc2reader 解析值，判断该字段能否导出。

    Args:
        - raw_value (object): 原始统计值，缺失时为 None。
        - parsed_value (object): 解析器处理后的对应字段值。

    Returns:
        - result (dict): 包含原始值 raw、解析值 parsed、可用值 value、
          检查状态 status 和原始值与解析值是否不同的 parser_changed。
          只有两值一致且原始值为非负整数时，value 才保留原始值。
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
