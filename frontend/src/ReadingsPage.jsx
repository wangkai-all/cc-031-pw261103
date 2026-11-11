import { useState } from 'react'
import { api } from './api'
import { useLoad, MeterSelect, CsvUpload } from './shared'
import { FLAG_TEXT } from './theme'

export default function ReadingsPage({ meters, meterId, setMeterId }) {
  const { data, loading, reload } = useLoad(
    () => (meterId ? api.readings(meterId) : Promise.resolve([])),
    [meterId])
  const [form, setForm] = useState({
    read_at: '', reading_kwh: '', flag: 'normal', note: '',
  })
  const [err, setErr] = useState('')

  const submit = async () => {
    setErr('')
    try {
      await api.addReading(meterId, {
        read_at: form.read_at.replace('T', ' ') + ':00',
        reading_kwh: form.reading_kwh,
        flag: form.flag,
        note: form.note,
      })
      setForm({ read_at: '', reading_kwh: '', flag: 'normal', note: '' })
      reload()
    } catch (e) {
      setErr(e.message)
    }
  }

  return (
    <div>
      <div className="card">
        <div className="row">
          <MeterSelect meters={meters} value={meterId} onChange={setMeterId} />
        </div>
      </div>
      {!meterId ? <div className="card muted">请先选择电表。</div> : (
        <>
          <div className="card">
            <h2>手工录入读数（北京时间）</h2>
            <div className="row">
              <div className="field">
                <label>读取时间</label>
                <input type="datetime-local" step={60} value={form.read_at}
                  onChange={(e) => setForm({ ...form,
                    read_at: e.target.value })} />
              </div>
              <div className="field">
                <label>累计读数 (kWh)</label>
                <input type="number" step="0.000001" placeholder="如 1023.45"
                  value={form.reading_kwh}
                  onChange={(e) => setForm({ ...form,
                    reading_kwh: e.target.value })} />
              </div>
              <div className="field">
                <label>标记</label>
                <select value={form.flag}
                  onChange={(e) => setForm({ ...form,
                    flag: e.target.value })}>
                  {Object.entries(FLAG_TEXT).map(([k, v]) =>
                    <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
              <div className="field">
                <label>备注</label>
                <input value={form.note}
                  onChange={(e) => setForm({ ...form, note: e.target.value })} />
              </div>
              <button className="btn primary"
                disabled={!form.read_at || form.reading_kwh === ''}
                onClick={submit}>录入</button>
            </div>
            {err && <p className="msg-err">{err}</p>}
          </div>

          <div className="card">
            <h2>CSV 批量导入</h2>
            <CsvUpload templateName="readings"
              onUpload={(f) => api.importReadings(meterId, f).then((r) => {
                reload(); return r
              })} />
          </div>

          <div className="card">
            <h2>读数列表（{data?.length || 0} 条）{loading && ' 加载中…'}</h2>
            <div className="scroll-x">
              <table>
                <thead>
                  <tr>
                    <th>时间（北京时间）</th>
                    <th className="num">累计读数(kWh)</th>
                    <th>标记</th><th>备注</th>
                  </tr>
                </thead>
                <tbody>
                  {(data || []).map((r) => (
                    <tr key={r.id}>
                      <td className="mono">{r.read_at}</td>
                      <td className="num mono">{r.reading_kwh}</td>
                      <td><span className={`badge ${
                        r.flag === 'normal' ? 'ok' : 'break'}`}>
                        {FLAG_TEXT[r.flag]}
                      </span></td>
                      <td className="muted">{r.note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
