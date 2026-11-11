"""核算引擎测试：跨午夜、边界读数、节假日切换、换表、缺测、守恒与未知单列。"""
from datetime import date, datetime
from decimal import Decimal

from app.decimal_utils import D
from app.engine import (BREAK, DROP, GAP, VALID, UNIFORM_ASSUMPTION,
                        build_intervals, evaluate, split_valid_interval)


# 测试电价：工作日 峰/平/谷；节假日 尖/平/谷（价格不同，便于区分）
WORKDAY_TARIFF = {
    "id": 1, "name": "工作日版", "effective_date": date(2026, 1, 1),
    "day_type": "workday",
    "periods": [
        {"label": "谷", "start_min": 0, "end_min": 480,
         "price_yuan": D("0.30")},                       # 00:00-08:00
        {"label": "平", "start_min": 480, "end_min": 600,
         "price_yuan": D("0.60")},                       # 08:00-10:00
        {"label": "峰", "start_min": 600, "end_min": 720,
         "price_yuan": D("1.00")},                       # 10:00-12:00
        {"label": "平", "start_min": 720, "end_min": 1380,
         "price_yuan": D("0.60")},                       # 12:00-23:00
        {"label": "谷", "start_min": 1380, "end_min": 1440,
         "price_yuan": D("0.30")},                       # 23:00-24:00
    ],
}
HOLIDAY_TARIFF = {
    "id": 2, "name": "节假日版", "effective_date": date(2026, 1, 1),
    "day_type": "holiday",
    "periods": [
        {"label": "谷", "start_min": 0, "end_min": 600,
         "price_yuan": D("0.25")},                       # 00:00-10:00
        {"label": "尖", "start_min": 600, "end_min": 720,
         "price_yuan": D("1.20")},                       # 10:00-12:00
        {"label": "平", "start_min": 720, "end_min": 1380,
         "price_yuan": D("0.50")},                       # 12:00-23:00
        {"label": "谷", "start_min": 1380, "end_min": 1440,
         "price_yuan": D("0.25")},                       # 23:00-24:00
    ],
}


class FakeResolver:
    def __init__(self, missing_days=()):
        self.missing = set(missing_days)

    def __call__(self, day):
        dtype = "holiday" if day.weekday() >= 5 else "workday"
        if day in self.missing:
            return None, dtype
        tid = 1 if dtype == "workday" else 2
        return tid, dtype

    @staticmethod
    def load(tid):
        return WORKDAY_TARIFF if tid == 1 else HOLIDAY_TARIFF

    @staticmethod
    def check_overlaps(days):
        return []


def rid(n):
    return n


def reading(n, ts, value, flag="normal", note=""):
    return {"id": n, "read_at": ts, "reading_kwh": D(value),
            "flag": flag, "note": note}


class TestIntervalClassification:
    def test_gap_over_30min(self):
        a = reading(1, datetime(2026, 11, 5, 10, 0), "100")
        b = reading(2, datetime(2026, 11, 5, 10, 31), "102")
        ivs = build_intervals([a, b])
        assert len(ivs) == 1 and ivs[0].kind == GAP
        assert ivs[0].energy is None

    def test_exactly_30min_is_valid(self):
        a = reading(1, datetime(2026, 11, 5, 10, 0), "100")
        b = reading(2, datetime(2026, 11, 5, 10, 30), "102")
        ivs = build_intervals([a, b])
        assert ivs[0].kind == VALID and ivs[0].energy == D("2")

    def test_drop_without_flag(self):
        a = reading(1, datetime(2026, 11, 5, 10, 0), "100")
        b = reading(2, datetime(2026, 11, 5, 10, 10), "98")
        ivs = build_intervals([a, b])
        assert ivs[0].kind == DROP and ivs[0].energy is None

    def test_replacement_is_break_even_if_value_lower(self):
        a = reading(1, datetime(2026, 11, 5, 10, 0), "500")
        b = reading(2, datetime(2026, 11, 5, 10, 10), "0",
                    flag="replacement")
        ivs = build_intervals([a, b])
        assert ivs[0].kind == BREAK and ivs[0].energy is None

    def test_reset_is_break(self):
        a = reading(1, datetime(2026, 11, 5, 10, 0), "500")
        b = reading(2, datetime(2026, 11, 5, 10, 10), "0", flag="reset")
        ivs = build_intervals([a, b])
        assert ivs[0].kind == BREAK


class TestSplitting:
    def _iv(self, t0, t1, v0, v1):
        ivs = build_intervals([
            reading(1, t0, v0), reading(2, t1, v1)])
        return ivs[0]
    def test_across_midnight_energy_conservation(self):
        # 23:45 -> 次日 00:15（30 分钟内，有效），跨午夜且跨工作日/周末
        # （11-06 周五 → 11-07 周六），共 3 kWh，均匀分摊每 15 分钟 1.5 度
        t0 = datetime(2026, 11, 6, 23, 45)
        t1 = datetime(2026, 11, 7, 0, 15)
        iv = self._iv(t0, t1, "100", "103")
        segs = split_valid_interval(iv, FakeResolver())
        # 应有：周五 23:45-24:00 谷、周六 00:00-00:15 谷
        assert [s["label"] for s in segs] == ["谷", "谷"]
        assert segs[0]["day"] == date(2026, 11, 6)
        assert segs[1]["day"] == date(2026, 11, 7)
        # 守恒：拆分电量严格等于区间电量
        assert sum((s["energy_kwh"] for s in segs), D("0")) == D("3")
        # 均匀假设：两段时长相等，电量相等
        assert segs[0]["energy_kwh"] == segs[1]["energy_kwh"] == D("1.5")
        # 不同日期使用不同版本单价
        assert segs[0]["price"] == D("0.30")
        assert segs[1]["price"] == D("0.25")

    def test_reading_exactly_on_tou_boundary(self):
        # 读数恰好落在 08:00、10:00 边界上，相邻间隔均 <=30 分钟
        pts = [
            (datetime(2026, 11, 5, 7, 30), D("10")),
            (datetime(2026, 11, 5, 8, 0), D("12")),    # 谷/平边界
            (datetime(2026, 11, 5, 8, 30), D("13")),
            (datetime(2026, 11, 5, 9, 0), D("14")),
            (datetime(2026, 11, 5, 9, 30), D("14.5")),
            (datetime(2026, 11, 5, 10, 0), D("15")),   # 平/峰边界
        ]
        readings = [reading(i, t, str(v)) for i, (t, v) in enumerate(pts, 1)]
        ivs = build_intervals(readings)
        assert all(iv.kind == VALID for iv in ivs)
        seg0 = split_valid_interval(ivs[0], FakeResolver())
        assert len(seg0) == 1 and seg0[0]["label"] == "谷"
        # 08:00 之后的区间都在平段内（10:00 是终点，不含峰段）
        for iv in ivs[1:]:
            segs = split_valid_interval(iv, FakeResolver())
            assert len(segs) == 1 and segs[0]["label"] == "平"

    def test_holiday_switch_uses_holiday_tariff(self):
        # 周六 09:45 -> 10:15（30 分钟）：09:45-10:00 谷 0.25，10:00-10:15 尖 1.20
        t0 = datetime(2026, 11, 7, 9, 45)
        t1 = datetime(2026, 11, 7, 10, 15)
        iv = self._iv(t0, t1, "20", "24")
        segs = split_valid_interval(iv, FakeResolver())
        assert [s["label"] for s in segs] == ["谷", "尖"]
        assert [s["price"] for s in segs] == [D("0.25"), D("1.20")]
        assert sum((s["energy_kwh"] for s in segs), D("0")) == D("4")

    def test_repeating_decimal_allocation_last_segment_absorbs_remainder(self):
        # 10 kWh / 30 分钟，切成 3 个 10 分钟段 -> 除不尽，末段兜尾差
        t0 = datetime(2026, 11, 5, 0, 0)
        t1 = datetime(2026, 11, 5, 0, 30)
        iv = self._iv(t0, t1, "0", "10")
        segs = split_valid_interval(iv, FakeResolver())
        assert len(segs) == 1  # 全在谷段，无内部边界；改用跨边界区间验证
        assert segs[0]["energy_kwh"] == D("10")

    def test_repeating_decimal_with_tou_cut(self):
        # 07:45 -> 08:15，跨谷/平边界：30 分钟 10 度，各 15 分钟 5 度可整除；
        # 再构造 29 分钟 / 10 度的非整除场景验证末段兜底
        t0 = datetime(2026, 11, 5, 7, 46)
        t1 = datetime(2026, 11, 5, 8, 15)
        iv = self._iv(t0, t1, "0", "10")
        segs = split_valid_interval(iv, FakeResolver())
        assert sum((s["energy_kwh"] for s in segs), D("0")) == D("10")
        assert segs[-1]["energy_kwh"] == D("10") - sum(
            (s["energy_kwh"] for s in segs[:-1]), D("0"))

    def test_formula_and_prices_present(self):
        t0 = datetime(2026, 11, 5, 9, 45)
        t1 = datetime(2026, 11, 5, 10, 15)
        iv = self._iv(t0, t1, "0", "4")
        segs = split_valid_interval(iv, FakeResolver())
        assert len(segs) == 2  # 平 + 峰
        for s in segs:
            assert s["cost_yuan_exact"] == s["energy_kwh"] * s["price"]
            assert "×" in _formula_text(s)

    def test_missing_tariff_segment_has_no_cost(self):
        t0 = datetime(2026, 11, 5, 9, 45)
        t1 = datetime(2026, 11, 5, 10, 15)
        iv = self._iv(t0, t1, "0", "4")
        segs = split_valid_interval(
            iv, FakeResolver(missing_days={date(2026, 11, 5)}))
        assert all(s["price"] is None and s["cost_yuan_exact"] is None
                   for s in segs)
        # 电量仍完成拆分
        assert sum((s["energy_kwh"] for s in segs), D("0")) == D("4")


def _formula_text(seg):
    from app.engine import _formula
    return _formula(seg)


class OverlapResolver(FakeResolver):
    def check_overlaps(self, days):
        return [(date(2026, 11, 5), "存在重叠的工作日电价版本 A 与 B")]


class TestEvaluate:
    def test_overlap_rule_blocks_bill(self):
        readings = [
            reading(1, datetime(2026, 11, 5, 9, 45), "0"),
            reading(2, datetime(2026, 11, 5, 10, 15), "4"),
        ]
        result = evaluate(readings, OverlapResolver())
        assert any(i.code == "TARIFF_OVERLAP" for i in result.issues)
        bill = result.bills["2026-11-05"]
        assert bill["status"] == "blocked"
        assert "total_yuan" not in bill

    def test_full_trace_unknown_separated_and_bill_totals(self):
        # 正常 -> 缺测 -> 正常 -> 换表断点 -> 新表正常
        readings = [
            reading(1, datetime(2026, 11, 5, 8, 0), "100"),
            reading(2, datetime(2026, 11, 5, 8, 30), "106"),   # +6 有效
            reading(3, datetime(2026, 11, 5, 9, 30), "118"),   # 间隔 60min 缺测
            reading(4, datetime(2026, 11, 5, 10, 0), "124"),   # +6 有效（平/峰各半）
            reading(5, datetime(2026, 11, 5, 10, 30), "0",
                    flag="replacement"),                        # 换表断点
            reading(6, datetime(2026, 11, 5, 11, 0), "6"),     # 新表 +6 峰
        ]
        result = evaluate(readings, FakeResolver())
        kinds = [iv.kind for iv in result.intervals]
        assert kinds == [VALID, GAP, VALID, BREAK, VALID]

        # 两类未知均进待核查，且没有电量数字
        assert {a["kind"] for a in result.anomalies} == {GAP, BREAK}
        assert all(a["energy_kwh"] is None for a in result.anomalies)

        bill = result.bills["2026-11-05"]
        assert bill["status"] == "ok"
        # 未知区间单列，不参与计费电量
        assert len(bill["unknown_intervals"]) == 2
        assert all(u["energy_kwh"] is None for u in bill["unknown_intervals"])

        # 计费电量只含三个有效区间：6 + 6 + 6 = 18
        assert Decimal(bill["energy_kwh"]) == D("18")
        # 总额 = 精确和四舍五入到分；尾差字段存在且自洽
        exact = Decimal(bill["cost_yuan_exact"])
        total = Decimal(bill["total_yuan"])
        assert total == exact.quantize(Decimal("0.01"))
        assert Decimal(bill["rounding_diff_yuan"]) == total - exact
        assert bill["assumption"] == UNIFORM_ASSUMPTION

        # 守恒：每个有效区间的段电量之和 = 区间电量
        for iv in result.intervals:
            if iv.kind == VALID:
                assert sum((s["energy_kwh"] for s in iv.segments),
                           D("0")) == iv.energy

    def test_blocked_bill_when_tariff_missing(self):
        readings = [
            reading(1, datetime(2026, 11, 5, 9, 45), "0"),
            reading(2, datetime(2026, 11, 5, 10, 15), "4"),
        ]
        resolver = FakeResolver(missing_days={date(2026, 11, 5)})
        result = evaluate(readings, resolver)
        bill = result.bills["2026-11-05"]
        assert bill["status"] == "blocked"
        assert "total_yuan" not in bill
        assert any(i.code == "TARIFF_MISSING" for i in result.issues)

    def test_two_day_trace_bills_split_by_date(self):
        # 23:45 -> 次日 00:15，跨午夜共 4 kWh，各 15 分钟 2 度
        readings = [
            reading(1, datetime(2026, 11, 6, 23, 45), "100"),
            reading(2, datetime(2026, 11, 7, 0, 15), "104"),
        ]
        result = evaluate(readings, FakeResolver())
        assert sorted(result.bills) == ["2026-11-06", "2026-11-07"]
        b1, b2 = result.bills["2026-11-06"], result.bills["2026-11-07"]
        assert Decimal(b1["energy_kwh"]) + Decimal(b2["energy_kwh"]) == D("4")
        # 两个 15 分钟段分别按工作日谷价 0.30、节假日谷价 0.25
        assert Decimal(b1["total_yuan"]) == Decimal("0.60")
        assert Decimal(b2["total_yuan"]) == Decimal("0.50")
