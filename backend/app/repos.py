"""数据访问层：封装全部 DuckDB SQL。"""
from datetime import date, datetime
from decimal import Decimal

from .db import tx
from .decimal_utils import D


# ---------------- 电表 ----------------
def list_meters() -> list[dict]:
    with tx() as c:
        rows = c.execute(
            "SELECT id, code, name FROM meters ORDER BY code"
        ).fetchall()
    return [{"id": r[0], "code": r[1], "name": r[2]} for r in rows]


def create_meter(code: str, name: str) -> dict:
    with tx() as c:
        try:
            cur = c.execute(
                "INSERT INTO meters(code, name) VALUES (?, ?) RETURNING id",
                [code, name],
            )
            mid = cur.fetchone()[0]
        except Exception as e:  # 唯一冲突
            raise ValueError(f"电表编码已存在: {code}") from e
    return {"id": mid, "code": code, "name": name}


# ---------------- 读数 ----------------
def insert_reading(meter_id: int, read_at: datetime,
                   reading_kwh: Decimal, flag: str, note: str) -> int:
    with tx() as c:
        try:
            cur = c.execute(
                """INSERT INTO readings(meter_id, read_at, reading_kwh, flag, note)
                   VALUES (?, ?, ?, ?, ?) RETURNING id""",
                [meter_id, read_at, reading_kwh, flag, note],
            )
            return cur.fetchone()[0]
        except Exception as e:
            raise ValueError(
                f"读数已存在或电表无效: meter={meter_id} time={read_at}"
            ) from e


def list_readings(meter_id: int) -> list[dict]:
    with tx() as c:
        rows = c.execute(
            """SELECT id, read_at, reading_kwh, flag, note
               FROM readings WHERE meter_id = ? ORDER BY read_at, id""",
            [meter_id],
        ).fetchall()
    return [
        {
            "id": r[0],
            "read_at": r[1],
            "reading_kwh": D(r[2]),
            "flag": r[3],
            "note": r[4],
        }
        for r in rows
    ]


# ---------------- 电价 ----------------
def create_tariff(name: str, effective_date: date, day_type: str,
                  note: str, periods: list[dict]) -> int:
    with tx() as c:
        try:
            tid = c.execute(
                """INSERT INTO tariffs(name, effective_date, day_type, note)
                   VALUES (?, ?, ?, ?) RETURNING id""",
                [name, effective_date, day_type, note],
            ).fetchone()[0]
        except Exception as e:
            raise ValueError(
                f"电价版本冲突: {effective_date} / {day_type} 已存在"
            ) from e
        c.executemany(
            """INSERT INTO tariff_periods(tariff_id, label, start_min, end_min, price_yuan)
               VALUES (?, ?, ?, ?, ?)""",
            [(tid, p["label"], p["start_min"], p["end_min"], D(p["price_yuan"]))
             for p in periods],
        )
        return tid


def delete_tariff(tariff_id: int) -> None:
    with tx() as c:
        c.execute("DELETE FROM tariffs WHERE id = ?", [tariff_id])


def list_tariffs() -> list[dict]:
    with tx() as c:
        rows = c.execute(
            """SELECT t.id, t.name, t.effective_date, t.day_type, t.note
               FROM tariffs t
               ORDER BY t.effective_date, t.day_type"""
        ).fetchall()
        result = []
        for r in rows:
            periods = c.execute(
                """SELECT label, start_min, end_min, price_yuan
                   FROM tariff_periods WHERE tariff_id = ?
                   ORDER BY start_min""",
                [r[0]],
            ).fetchall()
            result.append({
                "id": r[0],
                "name": r[1],
                "effective_date": r[2],
                "day_type": r[3],
                "note": r[4],
                "periods": [
                    {"label": p[0], "start_min": p[1], "end_min": p[2],
                     "price_yuan": D(p[3])}
                    for p in periods
                ],
            })
    return result


def resolve_tariff_id(day: date, day_type: str) -> int | None:
    """取生效日期 <= day 的最新同类型版本。"""
    with tx() as c:
        row = c.execute(
            """SELECT id FROM tariffs
               WHERE day_type = ? AND effective_date <= ?
               ORDER BY effective_date DESC LIMIT 1""",
            [day_type, day],
        ).fetchone()
    return row[0] if row else None


def load_tariff(tariff_id: int) -> dict | None:
    with tx() as c:
        row = c.execute(
            "SELECT id, name, effective_date, day_type, note FROM tariffs WHERE id = ?",
            [tariff_id],
        ).fetchone()
        if not row:
            return None
        periods = c.execute(
            """SELECT label, start_min, end_min, price_yuan
               FROM tariff_periods WHERE tariff_id = ? ORDER BY start_min""",
            [tariff_id],
        ).fetchall()
    return {
        "id": row[0],
        "name": row[1],
        "effective_date": row[2],
        "day_type": row[3],
        "note": row[4],
        "periods": [
            {"label": p[0], "start_min": p[1], "end_min": p[2],
             "price_yuan": D(p[3])}
            for p in periods
        ],
    }


# ---------------- 节假日日历 ----------------
def upsert_holiday(day: date, name: str, kind: str) -> None:
    with tx() as c:
        c.execute(
            """INSERT OR REPLACE INTO holidays(date, name, kind)
               VALUES (?, ?, ?)""",
            [day, name, kind],
        )


def delete_holiday(day: date) -> None:
    with tx() as c:
        c.execute("DELETE FROM holidays WHERE date = ?", [day])


def list_holidays() -> list[dict]:
    with tx() as c:
        rows = c.execute(
            "SELECT date, name, kind FROM holidays ORDER BY date"
        ).fetchall()
    return [{"date": r[0], "name": r[1], "kind": r[2]} for r in rows]
