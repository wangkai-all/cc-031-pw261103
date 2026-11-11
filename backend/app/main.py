"""FastAPI 入口：核算/读数/电价/日历 API，并托管前端构建产物。"""
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import repos, services
from .models import HolidayIn, MeterIn, ReadingIn, TariffIn
from .tariff_rules import validate_periods

app = FastAPI(title="分时电量核算", version="1.0")

FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


def _dec(x):
    return str(x) if x is not None else None


# ---------------------------------------------------------------- 电表
@app.get("/api/meters")
def get_meters():
    return repos.list_meters()


@app.post("/api/meters", status_code=201)
def post_meter(body: MeterIn):
    try:
        return repos.create_meter(body.code, body.name)
    except ValueError as e:
        raise HTTPException(409, str(e))


# ---------------------------------------------------------------- 读数
@app.get("/api/meters/{meter_id}/readings")
def get_readings(meter_id: int):
    rows = repos.list_readings(meter_id)
    return [{
        "id": r["id"],
        "read_at": r["read_at"].isoformat(),
        "reading_kwh": str(r["reading_kwh"]),
        "flag": r["flag"],
        "note": r["note"],
    } for r in rows]


@app.post("/api/meters/{meter_id}/readings", status_code=201)
def post_reading(meter_id: int, body: ReadingIn):
    try:
        rid = repos.insert_reading(
            meter_id, body.read_at, body.reading_kwh, body.flag, body.note)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"id": rid}


@app.post("/api/meters/{meter_id}/readings/import")
async def import_readings(meter_id: int, file: UploadFile = File(...)):
    raw = await file.read()
    try:
        return services.import_readings_csv(meter_id, raw)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------------------------------------------------------------- 电价
@app.get("/api/tariffs")
def get_tariffs():
    out = repos.list_tariffs()
    for t in out:
        t["effective_date"] = t["effective_date"].isoformat()
        for p in t["periods"]:
            p["price_yuan"] = str(p["price_yuan"])
    return out


@app.post("/api/tariffs", status_code=201)
def post_tariff(body: TariffIn):
    periods = [p.model_dump() for p in body.periods]
    errors = validate_periods(periods)
    if errors:
        raise HTTPException(422, {"errors": errors})
    try:
        tid = repos.create_tariff(
            body.name, body.effective_date, body.day_type,
            body.note, periods)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"id": tid}


@app.delete("/api/tariffs/{tariff_id}", status_code=204)
def remove_tariff(tariff_id: int):
    repos.delete_tariff(tariff_id)


@app.post("/api/tariffs/import")
async def import_tariffs(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        return services.import_tariffs_csv(raw)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------------------------------------------------------------- 日历
@app.get("/api/holidays")
def get_holidays():
    rows = repos.list_holidays()
    return [{"date": r["date"].isoformat(), "name": r["name"],
             "kind": r["kind"]} for r in rows]


@app.post("/api/holidays", status_code=201)
def post_holiday(body: HolidayIn):
    repos.upsert_holiday(body.date, body.name, body.kind)
    return {"ok": True}


@app.delete("/api/holidays/{day}", status_code=204)
def remove_holiday(day: str):
    try:
        d = datetime.strptime(day, "%Y-%m-%d").date()
    except ValueError as e:
        raise HTTPException(400, "日期格式应为 YYYY-MM-DD") from e
    repos.delete_holiday(d)


@app.post("/api/holidays/import")
async def import_holidays(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        return services.import_holidays_csv(raw)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------------------------------------------------------------- 核算
@app.get("/api/meters/{meter_id}/bills")
def get_bills(meter_id: int):
    return services.evaluate_meter(meter_id)


# ---------------------------------------------------------------- 导入模板
@app.get("/api/templates/readings.csv", response_class=PlainTextResponse)
def readings_template():
    return ("read_at,reading_kwh,flag,note\n"
            "2026-11-01 00:00:00,1000.000000,normal,\n"
            "2026-11-01 00:30:00,1001.500000,normal,\n"
            "2026-11-02 08:00:00,0.000000,replacement,换新表归零\n")


@app.get("/api/templates/tariffs.csv", response_class=PlainTextResponse)
def tariffs_template():
    return ("name,effective_date,day_type,label,start,end,price,note\n"
            "2026秋季工作日,2026-11-01,workday,谷,00:00,08:00,0.3200,\n"
            "2026秋季工作日,2026-11-01,workday,平,08:00,10:00,0.6800,\n")


@app.get("/api/templates/holidays.csv", response_class=PlainTextResponse)
def holidays_template():
    return ("date,kind,name\n"
            "2026-10-01,holiday,国庆节\n"
            "2026-10-10,workday,调休补班\n")


# ---------------------------------------------------------------- 前端托管
if FRONTEND_DIST.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="assets",
    )

    @app.get("/")
    def index():
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        # API 未命中仍由 FastAPI 返回 404；其余路径回退到 SPA
        if full_path.startswith("api/"):
            raise HTTPException(404)
        target = FRONTEND_DIST / full_path
        if target.is_file():
            return FileResponse(target)
        return FileResponse(FRONTEND_DIST / "index.html")
