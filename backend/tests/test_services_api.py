"""端到端测试：CSV 导入 -> 核算 -> 账单阻止/尾差/守恒（经 FastAPI 与 DuckDB）。"""
import datetime
from datetime import date
from decimal import Decimal

import pytest

from app import repos, services
from app.decimal_utils import D

READINGS_CSV = """read_at,reading_kwh,flag,note
2026-11-05 23:45:00,100.000000,normal,
2026-11-06 00:15:00,108.000000,normal,
2026-11-06 00:45:00,112.000000,normal,
2026-11-06 01:15:00,0.000000,replacement,换新表
2026-11-06 01:45:00,3.000000,normal,
2026-11-06 02:15:00,3.000000,normal,
"""

WORKDAY_CSV = """name,effective_date,day_type,label,start,end,price,note
秋季工作日,2026-01-01,workday,谷,00:00,08:00,0.3200,
秋季工作日,2026-01-01,workday,平,08:00,23:00,0.6800,
秋季工作日,2026-01-01,workday,谷,23:00,24:00,0.3200,
"""
HOLIDAY_CSV = """name,effective_date,day_type,label,start,end,price,note
秋季节假日,2026-01-01,holiday,谷,00:00,24:00,0.2500,
"""


@pytest.fixture
def seeded(temp_db):
    meter = repos.create_meter("M-001", "一号表")
    services.import_readings_csv(meter["id"], READINGS_CSV.encode())
    services.import_tariffs_csv(WORKDAY_CSV.encode())
    services.import_tariffs_csv(HOLIDAY_CSV.encode())
    return meter["id"]


def test_csv_imports(seeded):
    rows = repos.list_readings(seeded)
    assert len(rows) == 6
    assert rows[3]["flag"] == "replacement"


def test_evaluation_conservation_and_unknown(seeded):
    result = services.evaluate_meter(seeded)
    bills = {b["date"]: b for b in result["bills"]}

    # 2026-11-05（周四）：跨午夜区间 23:45-00:15 共 8 度，均匀分摊；
    # 当日占 15/30 -> 4 度，工作日谷价 0.32
    b5 = bills["2026-11-05"]
    assert b5["status"] == "ok"
    assert Decimal(b5["energy_kwh"]) == D("4")
    assert Decimal(b5["total_yuan"]) == Decimal("1.28")  # 4 * 0.32

    b6 = bills["2026-11-06"]
    # 00:00-00:15 谷 4 度（节假日 0.25）；00:15->00:45 +4 度谷；
    # 00:45->01:15 换表断点未知；换表后 01:45->02:15 用电 3 度谷
    assert Decimal(b6["energy_kwh"]) == D("11")
    unknown = b6["unknown_intervals"]
    assert len(unknown) == 1 and unknown[0]["kind"] == "break"
    assert unknown[0]["energy_kwh"] is None

    # 全局待核查区包含换表断点
    kinds = {a["kind"] for a in result["anomalies"]}
    assert "break" in kinds

    # 计费电量合计只覆盖有效区间：4(5日) + 4(跨午夜余下) + 4 + 3
    total_energy = sum(
        (Decimal(b["energy_kwh"]) for b in result["bills"]), D("0"))
    assert total_energy == D("15")  # 换表区间不计入


def test_missing_tariff_blocks_bill(temp_db):
    meter = repos.create_meter("M-002", "二号表")
    repos.insert_reading(meter["id"],
                         datetime.datetime(2026, 11, 5, 9, 45),
                         D("0"), "normal", "")
    repos.insert_reading(meter["id"],
                         datetime.datetime(2026, 11, 5, 10, 15),
                         D("4"), "normal", "")
    # 不导入任何电价
    result = services.evaluate_meter(meter["id"])
    bill = result["bills"][0]
    assert bill["date"] == "2026-11-05"
    assert bill["status"] == "blocked"
    assert result["issues"][0]["code"] == "TARIFF_MISSING"


def test_holiday_override_changes_day_type(temp_db, seeded):
    # 把 2026-11-05（周四）登记为节假日，应套用节假日电价 0.25
    repos.upsert_holiday(date(2026, 11, 5), "自定义假日", "holiday")
    result = services.evaluate_meter(seeded)
    b5 = next(b for b in result["bills"] if b["date"] == "2026-11-05")
    # 4 度全部按 0.25 = 1.00 元
    assert Decimal(b5["total_yuan"]) == Decimal("1.00")


def test_rounding_diff_is_disclosed(temp_db):
    # 09:45 -> 10:15（30 分钟有效区间）跨谷/平边界，各 15 分钟；
    # 1 度均匀分摊为 0.5 + 0.5，精确费用 0.5 元，验证尾差字段自洽
    meter = repos.create_meter("M-003", "三号表")
    repos.insert_reading(meter["id"], datetime.datetime(2026, 11, 5, 9, 45),
                         D("0"), "normal", "")
    repos.insert_reading(meter["id"], datetime.datetime(2026, 11, 5, 10, 15),
                         D("1"), "normal", "")
    repos.create_tariff("单日", date(2026, 1, 1), "workday", "", [
        {"label": "谷", "start_min": 0, "end_min": 600,
         "price_yuan": D("0.333")},   # 00:00-10:00
        {"label": "平", "start_min": 600, "end_min": 1440,
         "price_yuan": D("0.667")},   # 10:00-24:00
    ])
    result = services.evaluate_meter(meter["id"])
    bill = result["bills"][0]
    assert bill["date"] == "2026-11-05"
    assert bill["status"] == "ok"
    exact = Decimal(bill["cost_yuan_exact"])
    total = Decimal(bill["total_yuan"])
    assert total == exact.quantize(Decimal("0.01"))
    assert Decimal(bill["rounding_diff_yuan"]) == total - exact
    assert "ROUND_HALF_UP" in bill["rounding_rule"]
    # 0.5*0.333 + 0.5*0.667 = 0.5
    assert exact == Decimal("0.500000")
    assert total == Decimal("0.50")


def test_bad_tariff_csv_rejected(temp_db):
    bad = ("name,effective_date,day_type,label,start,end,price\n"
           "X,2026-01-01,workday,谷,00:00,10:00,0.3\n")  # 未覆盖全天
    out = services.import_tariffs_csv(bad.encode())
    assert out["inserted"] == 0 and out["errors"]


def test_duplicate_reading_skipped(temp_db):
    meter = repos.create_meter("M-004", "四号表")
    ts = datetime.datetime(2026, 11, 5, 9, 0)
    repos.insert_reading(meter["id"], ts, D("1"), "normal", "")
    out = services.import_readings_csv(
        meter["id"],
        b"read_at,reading_kwh\n2026-11-05 09:00:00,2\n")
    assert out["inserted"] == 0 and out["errors"]
