import { useMemo, useState } from 'react'
import { api } from './api'
import { useLoad, MeterSelect } from './shared'
import ReadingCurve from './ReadingCurve'
import { TouEnergyBars, DailyCostBars } from './TouBars'
import SegmentDetailModal from './SegmentDetailModal'
import { touColor, FLAG_TEXT, KIND_TEXT } from './theme'

export default function BillingPage({ meters, meterId, setMeterId }) {
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [expanded, setExpanded] = useState({})
  const [modalSeg, setModalSeg] = useState(null)
  const [modalBill, setModalBill] = useState(null)

  const { data: billsData, loading, error, reload } = useLoad(
    () => (meterId ? api.bills(meterId) : Promise.resolve(null)),
    [meterId])
  const { data: readings } = useLoad(
    () => (meterId ? api.readings(meterId) : Promise.resolve([])),
    [meterId])

  const bills = useMemo(() => {
    const all = billsData?.bills || []
    return all.filter((b) =>
      (!from || b.date >= from) && (!to || b.date <= to))
  }, [billsData, from, to])

  const okBills = bills.filter((b) => b.status === 'ok')
  const totals = useMemo(() => {
    const energy = okBills.reduce(
      (s, b) => s + Number(b.energy_kwh), 0)
    const amount = okBills.reduce(
      (s, b) => s + Number(b.total_yuan), 0)
    const unknown = bills.reduce(
      (s, b) => s + (b.unknown_intervals?.length || 0), 0)
    return { energy, amount, unknown }
  }, [bills])

  if (!meterId) {
    return <div className="card muted">请先在上方选择或创建一块电表。</div>
  }

  const toggle = (date, label) => {
    const key = label ? `${date}::${label}` : date
    setExpanded((p) => ({ ...p, [key]: !p[key] }))
  }

  return (
    <div>
      <div className="card">
        <div className="row">
          <MeterSelect meters={meters} value={meterId} onChange={setMeterId} />
          <div className="field">
            <label>起始日期</label>
            <input type="date" value={from}
              onChange={(e) => setFrom(e.target.value)} />
          </div>
          <div className="field">
            <label>结束日期</label>
            <input type="date" value={to}
              onChange={(e) => setTo(e.target.value)} />
          </div>
          <button className="btn" onClick={reload}>重新核算</button>
        </div>
      </div>

      {error && <div className="issues">加载失败：{error}</div>}
      {loading && <div className="card muted">核算中…</div>}

      {billsData?.issues?.length > 0 && (
        <div className="issues">
          <strong>账单阻止项（规则重叠或缺失，对应日期不出具金额）</strong>
          <ul>
            {billsData.issues.map((i, k) => (
              <li key={k}>[{i.code}] {i.date} — {i.message}</li>
            ))}
          </ul>
        </div>
      )}

      {billsData && (
        <>
          <div className="stat-grid">
            <div className="stat">
              <div className="k">账单天数</div>
              <div className="v">{bills.length}</div>
              <div className="sub">
                阻止 {bills.filter((b) => b.status === 'blocked').length} 天
              </div>
            </div>
            <div className="stat">
              <div className="k">计费电量合计</div>
              <div className="v">{totals.energy.toFixed(3)}</div>
              <div className="sub">kWh，仅含有效区间</div>
            </div>
            <div className="stat">
              <div className="k">账单金额合计</div>
              <div className="v">¥ {totals.amount.toFixed(2)}</div>
              <div className="sub">总额逐张舍入到分后求和</div>
            </div>
            <div className="stat">
              <div className="k">待核查区间</div>
              <div className="v">{totals.unknown}</div>
              <div className="sub">电量未知，始终单列不补零</div>
            </div>
          </div>

          <div className="card">
            <h2>累计读数曲线（北京时间）</h2>
            <ReadingCurve readings={readings || []}
              anomalies={billsData.anomalies} />
          </div>

          <div className="card">
            <h2>分时电量（kWh，按日堆叠）</h2>
            {okBills.length
              ? <TouEnergyBars bills={okBills} />
              : <p className="muted">暂无可出具的账单。</p>}
          </div>

          <div className="card">
            <h2>每日账单费用（元）</h2>
            {okBills.length
              ? <DailyCostBars bills={okBills} />
              : <p className="muted">暂无可出具的账单。</p>}
          </div>

          <h2 style={{ margin: '20px 4px 10px' }}>按日账单与计算明细</h2>
          {bills.map((b) => (
            <BillCard key={b.date} bill={b}
              expanded={expanded} toggle={toggle}
              onSegment={(seg) => { setModalSeg(seg); setModalBill(b) }} />
          ))}
          {!bills.length && <div className="card muted">该时间段内没有用电数据。</div>}
        </>
      )}

      <SegmentDetailModal segment={modalSeg} bill={modalBill}
        onClose={() => { setModalSeg(null); setModalBill(null) }} />
    </div>
  )
}

function BillCard({ bill: b, expanded, toggle, onSegment }) {
  const blocked = b.status === 'blocked'
  const keyOf = (label) => `${b.date}::${label}`
  return (
    <div className="card">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0 }}>
          {b.date}
          <span className={`badge ${blocked ? 'blocked' : 'ok'}`}
            style={{ marginLeft: 10 }}>
            {blocked ? '已阻止' : '正常出具'}
          </span>
        </h2>
        {!blocked && (
          <div>
            <span className="muted">账单总额：</span>
            <span className="fee-link"
              onClick={() => toggle(b.date)}>
              ¥ {b.total_yuan}
            </span>
            <span className="muted" style={{ marginLeft: 10 }}>
              精确 ¥ {b.cost_yuan_exact}
            </span>
          </div>
        )}
      </div>

      {blocked && (
        <ul style={{ color: 'var(--status-danger)', marginBottom: 0 }}>
          {b.issues.map((m, k) => <li key={k}>{m}</li>)}
        </ul>
      )}

      {!blocked && (
        <>
          <div className="row" style={{ marginTop: 10 }}>
            <span className="muted">
              计费电量 <strong className="mono">{b.energy_kwh}</strong> kWh
            </span>
            <span className="muted">
              尾差 <strong className="mono">{b.rounding_diff_yuan}</strong> 元
              （总额 − 未舍入之和）
            </span>
          </div>

          <div className="scroll-x" style={{ marginTop: 10 }}>
            <table>
              <thead>
                <tr>
                  <th>时段</th><th>单价(元/kWh)</th>
                  <th className="num">电量(kWh)</th>
                  <th className="num">精确费用(元)</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {b.tou_items.map((it) => (
                  <tr key={it.label}>
                    <td>
                      <span className="dot"
                        style={{ background: touColor(it.label),
                          marginRight: 6 }} />
                      {it.label}
                      <span className="muted"> · {it.tariff_name}</span>
                    </td>
                    <td className="num mono">{it.price_yuan}</td>
                    <td className="num mono">{it.energy_kwh}</td>
                    <td className="num">
                      <span className="fee-link"
                        onClick={() => toggle(b.date, it.label)}>
                        {it.cost_yuan_exact}
                      </span>
                    </td>
                    <td>
                      <button className="btn"
                        onClick={() => toggle(b.date, it.label)}>
                        {expanded[keyOf(it.label)] ? '收起明细' : '查看明细'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="assumption">{b.assumption}；{b.rounding_rule}</div>

          {/* 分时段明细（可由费用链接展开） */}
          {b.tou_items.map((it) => expanded[keyOf(it.label)] && (
            <SegmentTable key={it.label} bill={b} label={it.label}
              onSegment={onSegment} />
          ))}
          {expanded[b.date] && (
            <SegmentTable bill={b} label={null} onSegment={onSegment} />
          )}
        </>
      )}

      {/* 未知区间始终单列 */}
      {b.unknown_intervals?.length > 0 && (
        <div className="unknown-banner">
          当日有 {b.unknown_intervals.length} 个待核查区间，电量未知、不计入上表：
          <table style={{ marginTop: 8 }}>
            <thead>
              <tr>
                <th>类型</th><th>起</th><th>止</th>
                <th className="num">起点读数</th>
                <th className="num">终点读数</th><th>原因</th>
              </tr>
            </thead>
            <tbody>
              {b.unknown_intervals.map((u, k) => (
                <tr key={k}>
                  <td><span className={`badge ${u.kind}`}>
                    {KIND_TEXT[u.kind] || u.kind}
                  </span></td>
                  <td className="mono">{u.start_read_at}</td>
                  <td className="mono">{u.end_read_at}</td>
                  <td className="num mono">{u.start_reading_kwh}</td>
                  <td className="num mono">{u.end_reading_kwh}</td>
                  <td className="muted">{u.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function SegmentTable({ bill, label, onSegment }) {
  const segs = bill.segments.filter(
    (s) => label === null || s.label === label)
  return (
    <div className="scroll-x" style={{ marginTop: 10 }}>
      <table>
        <thead>
          <tr>
            <th>拆分时段</th><th>标签</th>
            <th className="num">时长(分)</th>
            <th className="num">单价</th>
            <th className="num">电量(kWh)</th>
            <th className="num">费用(元)</th>
            <th>公式</th>
          </tr>
        </thead>
        <tbody>
          {segs.map((s, k) => (
            <tr key={k}>
              <td className="mono" style={{ whiteSpace: 'normal' }}>
                {s.start}<br />→ {s.end}
              </td>
              <td>
                {s.label
                  ? <><span className="dot"
                      style={{ background: touColor(s.label),
                        marginRight: 6 }} />{s.label}</>
                  : <span className="badge blocked">缺电价</span>}
              </td>
              <td className="num mono">
                {Math.round(s.duration_s / 60)}
              </td>
              <td className="num mono">{s.price_yuan || '—'}</td>
              <td className="num mono">{s.energy_kwh}</td>
              <td className="num">
                {s.cost_yuan_exact
                  ? <span className="fee-link"
                      onClick={() => onSegment(s)}>
                      {s.cost_yuan_exact}
                    </span>
                  : '—'}
              </td>
              <td className="muted" style={{ whiteSpace: 'normal',
                maxWidth: 260 }}>{s.formula}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
