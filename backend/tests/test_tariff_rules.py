"""电价时段结构校验测试。"""
from app.decimal_utils import D
from app.tariff_rules import validate_periods


def p(label, s, e, price="0.5"):
    return {"label": label, "start_min": s, "end_min": e,
            "price_yuan": D(price)}


def test_full_day_coverage_ok():
    periods = [p("谷", 0, 480, "0.3"), p("平", 480, 1440, "0.6")]
    assert validate_periods(periods) == []


def test_overnight_valley_split_into_two_rows_ok():
    # 谷段跨午夜：23:00-24:00 与 00:00-06:00 同标签同价，平铺后无缺无重
    periods = [
        p("谷", 0, 360, "0.3"), p("峰", 360, 1380, "1.0"),
        p("谷", 1380, 1440, "0.3"),
    ]
    assert validate_periods(periods) == []


def test_gap_detected():
    errors = validate_periods([p("谷", 0, 400), p("平", 480, 1440)])
    assert any("缺口" in e for e in errors)


def test_overlap_detected():
    errors = validate_periods([p("谷", 0, 500), p("平", 480, 1440)])
    assert any("重叠" in e for e in errors)


def test_not_covering_full_day():
    errors = validate_periods([p("谷", 0, 1000)])
    assert any("未覆盖全天" in e for e in errors)


def test_negative_price_rejected():
    errors = validate_periods([p("谷", 0, 1440, "-0.1")])
    assert any("单价不能为负" in e for e in errors)
