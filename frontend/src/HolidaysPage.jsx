import { useState } from 'react'
import { api } from './api'
import { useLoad, CsvUpload } from './shared'

export default function HolidaysPage() {
  const { data, reload } = useLoad(() => api.holidays())
  const [form, setForm] = useState({ date: '', kind: 'holiday', name: '' })
  const [err, setErr] = useState('')

  return (
    <div>
      <div className="card">
        <h2>节假日 / 调休日历</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          登记为「节假日」的日期按节假日电价结算；登记为「补班」的周末按工作日电价结算。
          未登记日期按周一至周五工作日、周六周日节假日处理。全部时间统一北京时间。
        </p>
        <div className="row">
          <div className="field">
            <label htmlFor="holiday-date">日期</label>
            <input id="holiday-date" type="date" value={form.date}
              onChange={(e) => setForm({ ...form, date: e.target.value })} />
          </div>
          <div className="field">
            <label>类型</label>
            <select value={form.kind}
              onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                <option value="holiday">节假日</option>
                <option value="workday">调休补班</option>
              </select>
            </div>
          <div className="field">
            <label>名称</label>
            <input placeholder="如 国庆节" value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <button className="btn primary" disabled={!form.date}
            onClick={async () => {
              setErr('')
              try {
                await api.addHoliday(form)
                setForm({ date: '', kind: 'holiday', name: '' })
                reload()
              } catch (e) { setErr(e.message) }
            }}>登记</button>
        </div>
        {err && <p className="msg-err">{err}</p>}
      </div>

      <div className="card">
        <h2>CSV 导入</h2>
        <CsvUpload templateName="holidays"
          onUpload={async (f) => { const r = await api.importHolidays(f)
            reload(); return r }} />
      </div>

      <div className="card">
        <h2>已登记日期（{data?.length || 0}）</h2>
        <table>
          <thead>
            <tr><th>日期</th><th>类型</th><th>名称</th><th></th></tr>
          </thead>
          <tbody>
            {(data || []).map((h) => (
              <tr key={h.date}>
                <td className="mono">{h.date}</td>
                <td>
                  <span className={`badge ${h.kind === 'holiday'
                    ? 'gap' : 'ok'}`}>
                    {h.kind === 'holiday' ? '节假日' : '调休补班'}
                  </span>
                </td>
                <td>{h.name}</td>
                <td>
                  <button className="btn danger"
                    onClick={async () => {
                      await api.deleteHoliday(h.date); reload()
                    }}>删除</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
