# 分时电量核算平台

导入单向电表的累计读数与分时电价规则，按电表、日期查看电量、分时费用与逐段
计算明细。后端 Python + DuckDB + FastAPI 负责核算，前端 React + ECharts
展示读数曲线与账单。**所有时间统一使用北京时间（UTC+8）的 naive datetime。**

## 核算规则

1. **区间识别**：相邻有效读数形成一个用电区间，间隔最多 30 分钟。
   - 间隔 **超过 30 分钟** → `gap` 缺测区间，电量未知，进待核查，**不补零**；
   - 无清零/换表标记却**读数下降** → `drop` 异常，电量未知，进待核查；
   - 带 `reset`（清零）或 `replacement`（换表）标记的读数是**新起点**，
     与前一读数之间为 `break` 断点，跨断点电量未知、始终单列。
2. **均匀耗电假设**：有效区间内假定耗电均匀。区间跨自然日零点、电价版本
   生效边界或峰谷时段边界时先切开，再按各段时长比例分摊区间总电量；
   最后一段承担尾差，保证**拆分电量之和严格等于原区间电量**。该假设会
   显示在每张账单与费用明细中。
3. **电价**：含生效日期、工作日/节假日类型、一天内 0–1440 分钟的分时
   时段，时段必须无缝、无重叠覆盖全天，否则版本不予创建；某天找不到
   适用版本（规则缺失）或存在重叠版本时，**对应日期账单被阻止**，
   不出具金额，只展示问题与已拆分明细。
4. **精度**：电量与费用全程使用 Python `Decimal`（38 位精度），禁止
   float 直转；中间费用不舍入，仅在**账单总额处按 ROUND_HALF_UP 舍入
   到分**，并展示 `rounding_diff`（舍入后总额 − 未舍入费用之和）。
5. **日历**：未登记日期按周一至周五=工作日、周末=节假日；可登记
   `holiday`（法定假日）或 `workday`（调休补班）覆盖默认规则。

## 目录结构

```
backend/
  app/
    config.py          # 路径、30 分钟阈值、精度配置
    decimal_utils.py   # Decimal 工具与舍入规则
    db.py              # DuckDB 连接与建表
    models.py          # Pydantic 入参模型
    repos.py           # SQL 数据访问层
    tariff_rules.py    # 时段无缝/重叠/全天覆盖校验
    calendar.py        # 日期 -> workday/holiday
    engine.py          # 核算引擎（区间识别、切分、分摊、计价）
    services.py        # 电价解析、核算编排、CSV 导入
    main.py            # FastAPI 路由 + 前端静态托管
  tests/               # pytest（29 个用例）
  scripts/smoke.sh     # HTTP 端到端冒烟
frontend/
  src/                 # React 页面、ECharts 图表、费用明细弹窗
  test/                # Vitest + jsdom 组件端到端（5 个用例）
samples/               # 读数/电价/节假日示例 CSV
```

## 快速开始

```bash
# 后端
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend

# 前端（开发，代理 /api 到 8000）
cd frontend && npm install && npm run dev
# 或构建后由 FastAPI 直接托管（访问 http://127.0.0.1:8000/）
npm run build
```

## 测试

```bash
# 后端：跨午夜、边界读数、节假日、换表、缺测/下降、守恒、阻止、尾差
cd backend && /path/.venv/bin/python -m pytest tests -q

# 后端 HTTP 冒烟（需先启动服务，会写入演示数据）
bash backend/scripts/smoke.sh

# 前端组件端到端（jsdom，需后端在 127.0.0.1:8000 运行）
cd frontend && npm test
```

## CSV 格式

- 读数：`read_at,reading_kwh,flag,note`，`flag` 取 `normal/reset/replacement`
  （兼容中文 `正常/清零/换表`）。
- 电价：`name,effective_date,day_type,label,start,end,price,note`，
  同一 `(effective_date, day_type)` 的多行组成一个版本；`start/end`
  支持 `HH:MM` 或分钟数，`end=24:00`（1440）表示当天结束。
- 节假日：`date,kind,name`，`kind` 取 `holiday/workday`。

页面内提供三类 CSV 模板下载（`/api/templates/*.csv`）。

## 费用明细

账单中每个分时费用均可点击，弹窗展示：所属区间的**两端读数**与总电量/
总时长、拆分时段起讫、单价、分摊电量、精确费用与完整公式；账单总额的
舍入规则与尾差在账单卡片底部说明。待核查区间（缺测/下降/断点）在
每张账单内**单独成区**，只列两端读数与原因，`energy_kwh` 恒为 `null`。
