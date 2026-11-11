"""应用服务：电价解析、核算编排、CSV 导入。"""
import csv
import io
from datetime import date, datetime

from . import repos
from .calendar import override_map
from .decimal_utils import D
from .engine import evaluate
from .tariff_rules import validate_periods

TS_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S",
              "%Y/%m/%d %H:%M")
FLAG_ALIAS = {
    "normal": "normal", "": "normal", "正常": "normal",
    "reset": "reset", "清零": "reset",
    "replacement": "replacement", "换表": "replacement", "更换": "replacement",
}
KIND_ALIAS = {"holiday": "holiday", "节假日": "holiday",
              "workday": "workday", "工作日": "workday", "补班": "workday"}


class TariffResolver:
    """带缓存的电价解析。

    协议：__call__(day) -> (tariff_id | None, day_type)；
    load(tid) 取版本详情；check_overlaps(days) 检查重叠版本。
    """

    def __init__(self):
        self._cache: dict[date, tuple[int | None, str]] = {}
        self._omap = override_map()

    def __call__(self, day: date) -> tuple[int | None, str]:
        if day not in self._cache:
            dtype = self._day_type(day)
            self._cache[day] = (repos.resolve_tariff_id(day, dtype), dtype)
        return self._cache[day]

    def load(self, tariff_id: int) -> dict:
        return repos.load_tariff(tariff_id)

    def check_overlaps(self, days: list[date]):
        """同一生效日期 + 日类型的重复版本属于规则重叠。"""
        tariffs = repos.list_tariffs()
        seen: dict[tuple[date, str], str] = {}
        overlaps = []
        for t in tariffs:
            key = (t["effective_date"], t["day_type"])
            if key in seen:
                overlaps.append((
                    t["effective_date"],
                    f"存在重叠的{_cn(t['day_type'])}电价版本 "
                    f"“{seen[key]}”与“{t['name']}”",
                ))
            else:
                seen[key] = t["name"]
        return overlaps

    @staticmethod
    def _day_type(day: date) -> str:
        kind = override_map().get(day)
        if kind == "workday":
            return "workday"
        if kind == "holiday":
            return "holiday"
        return "workday" if day.weekday() < 5 else "holiday"


def _cn(t: str) -> str:
    return "工作日" if t == "workday" else "节假日"


def evaluate_meter(meter_id: int) -> dict:
    readings = repos.list_readings(meter_id)
    result = evaluate(readings, TariffResolver())
    return {
        "meter_id": meter_id,
        "reading_count": len(readings),
        "bills": [result.bills[k] for k in sorted(result.bills)],
        "anomalies": result.anomalies,
        "issues": [{"code": i.code, "date": i.date, "message": i.message}
                   for i in result.issues],
    }


# ---------------------------------------------------------------- CSV 导入
def _parse_ts(text: str) -> datetime:
    text = text.strip()
    for fmt in TS_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"无法解析时间: {text!r}")


def import_readings_csv(meter_id: int, raw: bytes) -> dict:
    """读数 CSV：read_at, reading_kwh, flag(可选), note(可选)。全量校验后写入。"""
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("CSV 缺少表头")
    headers = {h.strip().lower() for h in reader.fieldnames}
    if not {"read_at", "reading_kwh"}.issubset(headers):
        raise ValueError("读数 CSV 必须包含 read_at, reading_kwh 两列")

    rows, errors = [], []
    for i, row in enumerate(reader, start=2):
        try:
            flag = FLAG_ALIAS.get(
                (row.get("flag") or "").strip().lower(),
                None,
            )
            if flag is None:
                raise ValueError(f"未知标记: {row.get('flag')!r}")
            rows.append({
                "read_at": _parse_ts(row["read_at"]),
                "reading_kwh": D(row["reading_kwh"]),
                "flag": flag,
                "note": (row.get("note") or "").strip(),
            })
        except Exception as e:  # noqa: BLE001 - 收集后统一返回
            errors.append(f"第 {i} 行: {e}")
    if errors:
        return {"inserted": 0, "errors": errors}

    inserted, dup = 0, []
    for r in rows:
        try:
            repos.insert_reading(meter_id, **r)
            inserted += 1
        except ValueError:
            dup.append(r["read_at"].isoformat())
    return {
        "inserted": inserted,
        "errors": [f"重复读数已跳过: {t}" for t in dup],
    }


def _parse_minute(text: str) -> int:
    text = text.strip()
    if ":" not in text:
        value = int(text)
        if 0 <= value <= 1440:
            return value
        raise ValueError(f"分钟数越界: {text}")
    h, m = text.split(":")
    value = int(h) * 60 + int(m)
    if not 0 <= value <= 1440:
        raise ValueError(f"时间越界: {text}")
    return value


def import_tariffs_csv(raw: bytes) -> dict:
    """电价 CSV：name, effective_date, day_type, label, start, end, price, note(可选)。

    同一 (effective_date, day_type) 的多行组成一个版本；先做全天覆盖校验，
    任一版本非法则整批拒绝。
    """
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    required = {"name", "effective_date", "day_type", "label",
                "start", "end", "price"}
    if reader.fieldnames is None or not required.issubset(
            {h.strip().lower() for h in reader.fieldnames}):
        raise ValueError(f"电价 CSV 必须包含列: {sorted(required)}")

    grouped: dict[tuple, dict] = {}
    errors = []
    for i, row in enumerate(reader, start=2):
        try:
            eff = datetime.strptime(row["effective_date"].strip(),
                                    "%Y-%m-%d").date()
            dtype = KIND_ALIAS.get(row["day_type"].strip().lower())
            if dtype is None:
                raise ValueError(f"未知日类型: {row['day_type']!r}")
            key = (eff, dtype)
            version = grouped.setdefault(key, {
                "name": row["name"].strip(),
                "effective_date": eff, "day_type": dtype,
                "note": (row.get("note") or "").strip(),
                "periods": [],
            })
            version["periods"].append({
                "label": row["label"].strip(),
                "start_min": _parse_minute(row["start"]),
                "end_min": _parse_minute(row["end"]),
                "price_yuan": D(row["price"]),
            })
        except Exception as e:  # noqa: BLE001
            errors.append(f"第 {i} 行: {e}")

    for (eff, dtype), v in grouped.items():
        perr = validate_periods(v["periods"])
        errors.extend(f"{eff} {_cn(dtype)}: {m}" for m in perr)
    if errors:
        return {"inserted": 0, "errors": errors}

    inserted = 0
    for v in grouped.values():
        try:
            repos.create_tariff(**v)
            inserted += 1
        except ValueError as e:
            errors.append(str(e))
    return {"inserted": inserted, "errors": errors}


def import_holidays_csv(raw: bytes) -> dict:
    """节假日 CSV：date, kind(holiday/workday), name(可选)。"""
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "date" not in [
            h.strip().lower() for h in reader.fieldnames]:
        raise ValueError("节假日 CSV 必须包含 date 列")
    errors, rows = [], []
    for i, row in enumerate(reader, start=2):
        try:
            day = datetime.strptime(row["date"].strip(), "%Y-%m-%d").date()
            kind = KIND_ALIAS.get((row.get("kind") or "holiday").strip().lower())
            if kind is None:
                raise ValueError(f"未知 kind: {row.get('kind')!r}")
            rows.append((day, (row.get("name") or "").strip(), kind))
        except Exception as e:  # noqa: BLE001
            errors.append(f"第 {i} 行: {e}")
    if errors:
        return {"inserted": 0, "errors": errors}
    for day, name, kind in rows:
        repos.upsert_holiday(day, name, kind)
    return {"inserted": len(rows), "errors": []}
