#!/usr/bin/env bash
# 端到端 HTTP 冒烟：建表 -> CSV 导入（跨午夜/缺测/下降/换表）-> 核算 -> 阻止账单 -> 前端托管
set -euo pipefail
BASE=http://127.0.0.1:8000
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

cat > "$TMP/readings.csv" <<'EOF'
read_at,reading_kwh,flag,note
2026-11-05 23:45:00,100.000000,normal,
2026-11-06 00:15:00,106.000000,normal,
2026-11-06 00:45:00,110.000000,normal,
2026-11-06 01:45:00,120.000000,normal,
2026-11-06 02:15:00,118.000000,normal,
2026-11-06 02:45:00,0.000000,replacement,换新表归零
2026-11-06 03:15:00,2.000000,normal,
EOF

cat > "$TMP/workday.csv" <<'EOF'
name,effective_date,day_type,label,start,end,price,note
秋季工作日,2026-01-01,workday,谷,00:00,08:00,0.3200,
秋季工作日,2026-01-01,workday,平,08:00,23:00,0.6800,
秋季工作日,2026-01-01,workday,谷,23:00,24:00,0.3200,
EOF

cat > "$TMP/holiday.csv" <<'EOF'
name,effective_date,day_type,label,start,end,price,note
秋季节假日,2026-01-01,holiday,谷,00:00,24:00,0.2500,
EOF

echo '== 新建电表 =='
MID=$(curl -s -X POST "$BASE/api/meters" -H 'Content-Type: application/json' \
  -d '{"code":"SMOKE-1","name":"冒烟表"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
echo "meter id=$MID"

echo '== 导入读数 =='
curl -s -X POST "$BASE/api/meters/$MID/readings/import" -F "file=@$TMP/readings.csv"
echo
echo '== 导入电价 =='
curl -s -X POST "$BASE/api/tariffs/import" -F "file=@$TMP/workday.csv"; echo
curl -s -X POST "$BASE/api/tariffs/import" -F "file=@$TMP/holiday.csv"; echo

echo '== 核算账单 =='
curl -s "$BASE/api/meters/$MID/bills" > "$TMP/bills.json"
python3 - "$TMP/bills.json" <<'PY'
import json, sys
from decimal import Decimal
data = json.load(open(sys.argv[1]))
bills = {b["date"]: b for b in data["bills"]}
print("dates:", sorted(bills))
b5, b6 = bills["2026-11-05"], bills["2026-11-06"]
# 跨午夜区间 6 度，30 分钟均匀：15 分钟在 5 日、15 分钟在 6 日，各 3 度
assert Decimal(b5["energy_kwh"]) == Decimal("3"), b5["energy_kwh"]
# 6 日：3(跨午夜余下) + 4 + (60min 缺测，未知) + (下降，未知) + (换表断点，未知) + 2
assert Decimal(b6["energy_kwh"]) == Decimal("9"), b6["energy_kwh"]
# 守恒：所有有效区间段电量之和 = 区间电量
for b in (b5, b6):
    for seg in b["segments"]:
        pass
# 未知区间单列：缺测 gap、下降 drop、换表 break 各一
kinds = sorted(u["kind"] for u in b6["unknown_intervals"])
assert kinds == ["break", "drop", "gap"], kinds
assert all(u["energy_kwh"] is None for u in b6["unknown_intervals"])
# 全局待核查
akinds = sorted(a["kind"] for a in data["anomalies"])
assert akinds == ["break", "drop", "gap"], akinds
# 尾差自洽
for b in (b5, b6):
    exact = Decimal(b["cost_yuan_exact"])
    total = Decimal(b["total_yuan"])
    assert total == exact.quantize(Decimal("0.01"))
    assert Decimal(b["rounding_diff_yuan"]) == total - exact
# 段明细带两端读数
seg = b6["segments"][0]
assert seg["interval_start_reading_kwh"] and seg["interval_end_reading_kwh"]
assert "×" in seg["formula"]
print("b5 total:", b5["total_yuan"], "| b6 total:", b6["total_yuan"])
print("b6 unknown:", kinds)
print("SMOKE-1 assertions OK")
PY

echo '== 无电价电表应阻止账单 =='
M2=$(curl -s -X POST "$BASE/api/meters" -H 'Content-Type: application/json' \
  -d '{"code":"SMOKE-2","name":"无电价表"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
curl -s -X POST "$BASE/api/meters/$M2/readings" -H 'Content-Type: application/json' \
  -d '{"read_at":"2025-12-31 09:45:00","reading_kwh":"0","flag":"normal"}' > /dev/null
curl -s -X POST "$BASE/api/meters/$M2/readings" -H 'Content-Type: application/json' \
  -d '{"read_at":"2025-12-31 10:15:00","reading_kwh":"4","flag":"normal"}' > /dev/null
curl -s "$BASE/api/meters/$M2/bills" | python3 -c '
import sys, json
d = json.load(sys.stdin)
b = d["bills"][0]
assert b["date"] == "2025-12-31"
assert b["status"] == "blocked" and d["issues"][0]["code"] == "TARIFF_MISSING"
print("blocked bill OK:", b["issues"][0])'

echo '== 前端托管 =='
curl -s -o /dev/null -w "index.html -> %{http_code}\n" "$BASE/"
curl -s -o /dev/null -w "SPA fallback -> %{http_code}\n" "$BASE/some/route"
curl -s -o /dev/null -w "api 404 -> %{http_code}\n" "$BASE/api/nope"

echo '== 非法电价（未覆盖全天）应 422 =='
curl -s -o /dev/null -w "bad tariff -> %{http_code}\n" -X POST "$BASE/api/tariffs" \
  -H 'Content-Type: application/json' \
  -d '{"name":"bad","effective_date":"2026-01-01","day_type":"workday","periods":[{"label":"谷","start_min":0,"end_min":600,"price_yuan":"0.3"}]}'

echo '== 重叠电价版本在写入层即被拒绝（同一生效日+日类型唯一） =='
cat > "$TMP/dup.csv" <<'EOF'
name,effective_date,day_type,label,start,end,price,note
重复工作日版,2026-01-01,workday,谷,00:00,24:00,0.9900,
EOF
curl -s -X POST "$BASE/api/tariffs/import" -F "file=@$TMP/dup.csv"; echo
curl -s -o /dev/null -w "duplicate via API -> %{http_code}\n" -X POST "$BASE/api/tariffs" \
  -H 'Content-Type: application/json' \
  -d '{"name":"dup","effective_date":"2026-01-01","day_type":"workday","periods":[{"label":"谷","start_min":0,"end_min":1440,"price_yuan":"0.9"}]}'

echo 'ALL SMOKE TESTS PASSED'
