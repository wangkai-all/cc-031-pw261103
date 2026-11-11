"""分时电量核算引擎（纯函数风格，不直接访问数据库的部分可独立测试）。

核心约定
--------
1. 相邻有效读数形成一个用电区间；间隔 > 30 分钟为缺测区间（gap），
   无清零/换表标记却读数下降为异常下降（drop）。两类区间的电量未知，
   进入待核查，绝不补零。
2. reset / replacement 读数作为新起点，与前一读数之间形成断点（break），
   跨断点电量同样未知、单列。
3. 有效区间内按 *均匀耗电假设* 分摊：先在日期、电价版本、峰谷边界处
   切开，再按各段时长比例分配区间总电量；最后一段承担余数，保证
   拆分电量之和严格等于原区间电量。
4. 费用 = 段电量 × 段单价，中间不早舍入；仅在账单总额处按
   ROUND_HALF_UP 舍入到分，尾差（总额 - 未舍入之和）随账单展示。
5. 任一段找不到适用电价（规则缺失）或同日存在重叠版本时，对应日期的
   账单标记 blocked，不出具金额。
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from .config import MAX_GAP_SECONDS
from .decimal_utils import D, ZERO, display, to_cent

UNIFORM_ASSUMPTION = "区间内按均匀耗电假设，依各时段时长比例分摊电量"

# 区间类型
VALID = "valid"
GAP = "gap"          # 缺测 > 30 分钟
BREAK = "break"      # 换表/清零新起点
DROP = "drop"        # 无标记读数下降


@dataclass
class Reading:
    id: int
    read_at: datetime
    reading_kwh: Decimal
    flag: str
    note: str = ""


@dataclass
class Interval:
    kind: str
    start: Reading
    end: Reading
    duration_s: int
    energy: Decimal | None = None       # 仅 valid 有值
    reason: str = ""
    segments: list[dict] = field(default_factory=list)


@dataclass
class EngineIssue:
    code: str
    date: str
    message: str


# ---------------------------------------------------------------- 区间识别
def build_intervals(readings: list[dict]) -> list[Interval]:
    """把按时间排序的读数序列切成相邻对区间。"""
    pts = [
        Reading(
            id=r["id"], read_at=r["read_at"],
            reading_kwh=D(r["reading_kwh"]), flag=r["flag"],
            note=r.get("note", ""),
        )
        for r in readings
    ]
    intervals: list[Interval] = []
    for a, b in zip(pts, pts[1:]):
        if b.read_at <= a.read_at:
            # 同一时刻的重复读数：零时长，不形成区间
            continue
        duration = int((b.read_at - a.read_at).total_seconds())

        if b.flag in ("reset", "replacement"):
            intervals.append(Interval(
                kind=BREAK, start=a, end=b, duration_s=duration,
                reason=("换表" if b.flag == "replacement" else "清零")
                       + "：该读数为新起点，跨断点电量未知",
            ))
            continue

        delta = b.reading_kwh - a.reading_kwh
        if delta < 0:
            intervals.append(Interval(
                kind=DROP, start=a, end=b, duration_s=duration,
                reason=f"读数由 {a.reading_kwh} 下降至 {b.reading_kwh}，"
                       f"且无清零/换表标记，电量待核查",
            ))
            continue

        if duration > MAX_GAP_SECONDS:
            intervals.append(Interval(
                kind=GAP, start=a, end=b, duration_s=duration,
                reason=f"相邻读数间隔 {duration} 秒（>30 分钟），"
                       f"缺测期间电量未知，不补零",
            ))
            continue

        intervals.append(Interval(
            kind=VALID, start=a, end=b, duration_s=duration, energy=delta,
        ))
    return intervals


# ---------------------------------------------------------------- 切分点
def _day_start(dt: datetime) -> datetime:
    return datetime.combine(dt.date(), time.min)


def _at_minute(day: date, minute: int) -> datetime:
    """自然日 day 的第 minute 分钟对应的北京时间（支持 minute=1440）。"""
    return datetime.combine(day, time.min) + timedelta(minutes=minute)


def split_valid_interval(iv: Interval, tariff_lookup) -> list[dict]:
    """在日期、电价版本、峰谷边界处切开有效区间并分摊电量。

    tariff_lookup(day: date) -> (tariff_id, day_type) 或 (None, day_type)；
    同一次调用内还可能抛出 TariffOverlap 表示版本重叠。
    """
    start, end = iv.start.read_at, iv.end.read_at
    total_seconds = iv.duration_s
    total_energy = iv.energy

    # 1) 收集所有切分点：区间两端 + 每个自然日零点
    cuts = {start, end}
    cursor = _day_start(start) + timedelta(days=1)
    while cursor < end:
        cuts.add(cursor)
        cursor += timedelta(days=1)

    # 2) 每个自然日内，再按电价时段边界（分钟）切；电价版本切换点也
    #    体现在“日期 -> 版本”的映射变化上，零点切分已能覆盖版本边界。
    segments: list[dict] = []
    ordered = sorted(cuts)
    for seg_start, seg_end in zip(ordered, ordered[1:]):
        day = seg_start.date()
        tariff_id, day_type = tariff_lookup(day)
        minutes_start = seg_start.hour * 60 + seg_start.minute
        # seg_end 必在同一自然日内（零点已入 cuts）
        minutes_end = seg_end.hour * 60 + seg_end.minute
        if seg_end.date() != day:
            minutes_end = 1440
        segments.append({
            "start": seg_start, "end": seg_end,
            "day": day, "minutes_start": minutes_start,
            "minutes_end": minutes_end,
            "tariff_id": tariff_id, "day_type": day_type,
        })

    # 3) 按时段边界进一步细分（同日内）
    refined: list[dict] = []
    tariff_cache: dict[int, dict] = {}
    for seg in segments:
        tid = seg["tariff_id"]
        if tid is None:
            refined.append(seg | {"label": None, "price": None})
            continue
        if tid not in tariff_cache:
            tariff_cache[tid] = tariff_lookup.load(tid)
        tariff = tariff_cache[tid]
        periods = [
            p for p in tariff["periods"]
            if p["start_min"] < seg["minutes_end"]
            and p["end_min"] > seg["minutes_start"]
        ]
        for p in periods:
            ms = max(seg["minutes_start"], p["start_min"])
            me = min(seg["minutes_end"], p["end_min"])
            refined.append({
                "start": _at_minute(seg["day"], ms),
                "end": _at_minute(seg["day"], me),
                "day": seg["day"], "minutes_start": ms, "minutes_end": me,
                "tariff_id": tid, "day_type": seg["day_type"],
                "label": p["label"], "price": D(p["price_yuan"]),
                "tariff_name": tariff["name"],
            })

    # 4) 均匀耗电假设：按时长比例分配，末段兜尾差保证电量守恒
    allocated = ZERO
    for idx, seg in enumerate(refined):
        secs = int((seg["end"] - seg["start"]).total_seconds())
        seg["duration_s"] = secs
        # 所属有效区间的两端读数（供明细展示）
        seg["interval_start_at"] = start
        seg["interval_end_at"] = end
        seg["interval_start_reading_kwh"] = iv.start.reading_kwh
        seg["interval_end_reading_kwh"] = iv.end.reading_kwh
        seg["interval_total_energy_kwh"] = total_energy
        seg["interval_total_seconds"] = total_seconds
        if idx == len(refined) - 1:
            seg["energy_kwh"] = total_energy - allocated
        else:
            part = (total_energy * D(secs) / D(total_seconds))
            seg["energy_kwh"] = part
            allocated += part
        if seg["price"] is None:
            seg["cost_yuan_exact"] = None
        else:
            seg["cost_yuan_exact"] = seg["energy_kwh"] * seg["price"]
    return refined


class TariffOverlap(Exception):
    """同一 (日期, 日类型) 存在多个生效版本。"""


# ---------------------------------------------------------------- 引擎入口
@dataclass
class EngineResult:
    intervals: list[Interval]
    bills: dict[str, dict]          # date -> bill
    anomalies: list[dict]
    issues: list[EngineIssue]


def evaluate(readings: list[dict], lookup) -> EngineResult:
    """
    lookup 协议：
      lookup(day) -> (tariff_id | None, day_type)
      lookup.load(tariff_id) -> tariff dict
      lookup.check_overlaps(days) -> [(day, message)]（可选）
    """
    intervals = build_intervals(readings)
    issues: list[EngineIssue] = []
    anomalies: list[dict] = []
    day_segments: dict[str, list[dict]] = {}
    day_unknown: dict[str, list[dict]] = {}

    for iv in intervals:
        if iv.kind != VALID:
            anomalies.append(_anomaly(iv))
            day = iv.end.read_at.date().isoformat()
            day_unknown.setdefault(day, []).append({
                "kind": iv.kind,
                "reason": iv.reason,
                "start_read_at": iv.start.read_at.isoformat(),
                "end_read_at": iv.end.read_at.isoformat(),
                "start_reading_kwh": str(iv.start.reading_kwh),
                "end_reading_kwh": str(iv.end.reading_kwh),
                "duration_s": iv.duration_s,
                "energy_kwh": None,
            })
            continue

        refined = split_valid_interval(iv, lookup)
        iv.segments = refined
        for seg in refined:
            d = seg["day"].isoformat()
            if seg["tariff_id"] is None:
                issues.append(EngineIssue(
                    code="TARIFF_MISSING", date=d,
                    message=f"{d}（{_cn_day_type(seg['day_type'])}）"
                            f"缺少适用的电价版本，账单已阻止",
                ))
            day_segments.setdefault(d, []).append(seg)

    # 重叠版本检查：对覆盖到的每一天，校验同类型版本唯一
    covered_days = sorted(set(day_segments) | set(day_unknown))
    overlap_days = lookup.check_overlaps(
        [date.fromisoformat(d) for d in covered_days]
    ) if hasattr(lookup, "check_overlaps") else []
    for d, msg in overlap_days:
        issues.append(EngineIssue(
            code="TARIFF_OVERLAP", date=d.isoformat(),
            message=f"{d} {msg}，账单已阻止",
        ))

    blocked_dates = {i.date for i in issues}
    bills: dict[str, dict] = {}
    for d in covered_days:
        unknown = day_unknown.get(d, [])
        if d in blocked_dates:
            bills[d] = {
                "date": d, "status": "blocked",
                "issues": [i.message for i in issues if i.date == d],
                "unknown_intervals": unknown,
                "segments": _serialize_segments(day_segments.get(d, [])),
            }
            continue
        bills[d] = _build_bill(d, day_segments.get(d, []), unknown)

    return EngineResult(
        intervals=intervals, bills=bills,
        anomalies=anomalies, issues=issues,
    )


def _build_bill(day_str: str, segments: list[dict],
                unknown: list[dict]) -> dict:
    exact_total = ZERO
    energy_total = ZERO
    tou: dict[tuple, dict] = {}
    for seg in segments:
        exact_total += seg["cost_yuan_exact"]
        energy_total += seg["energy_kwh"]
        key = (seg["label"], seg["tariff_id"])
        item = tou.setdefault(key, {
            "label": seg["label"],
            "tariff_id": seg["tariff_id"],
            "tariff_name": seg["tariff_name"],
            "price_yuan": str(seg["price"]),
            "energy_kwh": ZERO,
            "cost_yuan_exact": ZERO,
        })
        item["energy_kwh"] += seg["energy_kwh"]
        item["cost_yuan_exact"] += seg["cost_yuan_exact"]

    total_rounded = to_cent(exact_total)
    rounding_diff = total_rounded - exact_total

    tou_items = sorted(tou.values(), key=lambda x: x["label"] or "")
    for item in tou_items:
        item["energy_kwh"] = display(item["energy_kwh"], 6)
        item["cost_yuan_exact"] = display(item["cost_yuan_exact"], 6)

    return {
        "date": day_str,
        "status": "ok",
        "energy_kwh": display(energy_total, 6),
        "cost_yuan_exact": display(exact_total, 6),
        "total_yuan": str(total_rounded),
        "rounding_diff_yuan": display(rounding_diff, 6),
        "rounding_rule": "各项费用按完整精度求和后，账单总额采用 ROUND_HALF_UP "
                         "舍入到分；尾差 = 舍入后总额 − 未舍入费用之和",
        "tou_items": tou_items,
        "segments": _serialize_segments(segments),
        "unknown_intervals": unknown,
        "assumption": UNIFORM_ASSUMPTION,
    }


def _serialize_segments(segments: list[dict]) -> list[dict]:
    out = []
    for s in segments:
        out.append({
            "start": s["start"].isoformat(),
            "end": s["end"].isoformat(),
            "duration_s": s["duration_s"],
            "label": s.get("label"),
            "price_yuan": (str(s["price"]) if s.get("price") is not None
                           else None),
            "tariff_id": s.get("tariff_id"),
            "tariff_name": s.get("tariff_name"),
            "day_type": s.get("day_type"),
            "energy_kwh": display(s["energy_kwh"], 6),
            "cost_yuan_exact": (
                display(s["cost_yuan_exact"], 6)
                if s.get("cost_yuan_exact") is not None else None
            ),
            "interval_start_at": s.get("interval_start_at").isoformat()
            if s.get("interval_start_at") else None,
            "interval_end_at": s.get("interval_end_at").isoformat()
            if s.get("interval_end_at") else None,
            "interval_start_reading_kwh": (
                str(s["interval_start_reading_kwh"])
                if s.get("interval_start_reading_kwh") is not None else None),
            "interval_end_reading_kwh": (
                str(s["interval_end_reading_kwh"])
                if s.get("interval_end_reading_kwh") is not None else None),
            "interval_total_energy_kwh": (
                display(s["interval_total_energy_kwh"], 6)
                if s.get("interval_total_energy_kwh") is not None else None),
            "interval_total_seconds": s.get("interval_total_seconds"),
            "formula": _formula(s),
        })
    return out


def _formula(seg: dict) -> str:
    if seg.get("price") is None:
        return "无适用电价：电量已拆分但无法计价"
    return (
        f"电量 = 区间总电量 × {seg['duration_s']}s / 区间总时长；"
        f"费用 = 电量 × {seg['price']} 元/kWh"
    )


def _anomaly(iv: Interval) -> dict:
    return {
        "kind": iv.kind,
        "reason": iv.reason,
        "start_id": iv.start.id,
        "end_id": iv.end.id,
        "start_read_at": iv.start.read_at.isoformat(),
        "end_read_at": iv.end.read_at.isoformat(),
        "start_reading_kwh": str(iv.start.reading_kwh),
        "end_reading_kwh": str(iv.end.reading_kwh),
        "duration_s": iv.duration_s,
        "energy_kwh": None,
    }


def _cn_day_type(t: str) -> str:
    return "工作日" if t == "workday" else "节假日"
