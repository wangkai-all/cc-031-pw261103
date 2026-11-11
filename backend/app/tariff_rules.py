"""电价时段结构校验：一天 0..1440 分钟必须无缝、无重叠地被覆盖。"""
from .decimal_utils import D


def validate_periods(periods: list[dict]) -> list[str]:
    """返回错误信息列表；空列表表示通过。

    允许同标签同单价的相邻时段（用于谷段跨午夜时拆成两条存储）。
    """
    errors: list[str] = []
    if not periods:
        return ["电价至少包含一个时段"]

    for p in periods:
        if not (0 <= p["start_min"] < p["end_min"] <= 1440):
            errors.append(
                f"时段 {p['label']} 边界非法: "
                f"{p['start_min']}..{p['end_min']}"
            )
        if D(p["price_yuan"]) < 0:
            errors.append(f"时段 {p['label']} 单价不能为负")
    if errors:
        return errors

    ordered = sorted(periods, key=lambda p: (p["start_min"], p["end_min"]))
    cursor = 0
    for p in ordered:
        if p["start_min"] > cursor:
            errors.append(
                f"时段存在缺口: {_hm(cursor)} 至 {_hm(p['start_min'])} 无价格"
            )
        elif p["start_min"] < cursor:
            errors.append(
                f"时段重叠: {p['label']} 起始 {_hm(p['start_min'])} "
                f"与此前时段冲突"
            )
        cursor = max(cursor, p["end_min"])
    if cursor != 1440:
        errors.append(f"时段未覆盖全天，结束于 {_hm(cursor)}，缺少至 24:00 的部分")
    return errors


def _hm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"
