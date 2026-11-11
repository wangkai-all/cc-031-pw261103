"""Decimal 高精度运算工具。

电量按完整精度的 Decimal 分摊，仅在最后一段做余数兜底，保证拆分电量之和
严格等于原区间电量；费用中间过程不舍入，仅在账单总额处按 ROUND_HALF_UP
舍入到分。
"""
from decimal import Decimal, ROUND_HALF_UP, getcontext

getcontext().prec = 38

ZERO = Decimal("0")
ONE = Decimal("1")
CENT = Decimal("0.01")


def D(value) -> Decimal:
    """把字符串/数字安全转为 Decimal（禁止 float 直转引入二进制误差）。"""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(str(value))


def round_half_up(value: Decimal, dp: int) -> Decimal:
    q = Decimal(1).scaleb(-dp)
    return value.quantize(q, rounding=ROUND_HALF_UP)


def to_cent(value: Decimal) -> Decimal:
    """账单总额舍入到分。"""
    return round_half_up(value, 2)


def display(value: Decimal, dp: int) -> str:
    """用于 API/页面展示的定小数字符串。"""
    return str(round_half_up(D(value), dp))
