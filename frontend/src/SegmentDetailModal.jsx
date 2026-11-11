import { touColor } from './theme'

/** 费用明细弹窗：展示两端读数、拆分时段、单价与计算公式。 */
export default function SegmentDetailModal({ segment, bill, onClose }) {
  if (!segment) return null
  const s = segment
  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true"
        onClick={(e) => e.stopPropagation()}>
        <button className="btn close" onClick={onClose}>关闭</button>
        <h3>费用计算明细 · {bill.date}</h3>

        <div className="card" style={{ boxShadow: 'none', marginBottom: 12 }}>
          <h2>所属用电区间（相邻有效读数）</h2>
          <table>
            <tbody>
              <tr>
                <th>起点读数</th>
                <td className="mono">
                  {s.interval_start_at} · {s.interval_start_reading_kwh} kWh
                </td>
              </tr>
              <tr>
                <th>终点读数</th>
                <td className="mono">
                  {s.interval_end_at} · {s.interval_end_reading_kwh} kWh
                </td>
              </tr>
              <tr>
                <th>区间总电量</th>
                <td className="mono">{s.interval_total_energy_kwh} kWh</td>
              </tr>
              <tr>
                <th>区间总时长</th>
                <td className="mono">
                  {s.interval_total_seconds} 秒
                  （{Math.round(s.interval_total_seconds / 60)} 分钟）
                </td>
              </tr>
            </tbody>
          </table>
          <div className="assumption">{bill.assumption}</div>
        </div>

        <div className="card" style={{ boxShadow: 'none' }}>
          <h2>
            本时段：
            {s.label
              ? <span><span className="dot"
                  style={{ background: touColor(s.label) }} /> {s.label}
                <span className="muted">（{s.tariff_name}）</span></span>
              : <span className="badge blocked">无适用电价</span>}
          </h2>
          <table>
            <tbody>
              <tr>
                <th>时段起讫（北京时间）</th>
                <td className="mono">{s.start} → {s.end}</td>
              </tr>
              <tr>
                <th>时长</th>
                <td className="mono">{s.duration_s} 秒
                  （{Math.round(s.duration_s / 60)} 分钟）</td>
              </tr>
              <tr>
                <th>单价</th>
                <td className="mono">
                  {s.price_yuan ? `¥ ${s.price_yuan} / kWh` : '—'}
                </td>
              </tr>
              <tr>
                <th>分摊电量</th>
                <td className="mono">{s.energy_kwh} kWh</td>
              </tr>
              <tr>
                <th>精确费用（未舍入）</th>
                <td className="mono">
                  {s.cost_yuan_exact ? `¥ ${s.cost_yuan_exact}` : '—'}
                </td>
              </tr>
            </tbody>
          </table>
          <div className="formula">
            <strong>公式：</strong>{s.formula}
            {s.label && (
              <div style={{ marginTop: 6 }}>
                费用 = {s.energy_kwh} × {s.price_yuan}
                = {s.cost_yuan_exact} 元；
                账单总额在汇总处按 ROUND_HALF_UP 舍入到分。
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
