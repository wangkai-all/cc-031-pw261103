import { useState } from 'react'
import { api } from './api'
import { useLoad, CsvUpload } from './shared'
import { touColor } from './theme'

const emptyPeriod = () => ({ label: '谷', start: '00:00', end: '08:00',
  price_yuan: '0.3200' })

export default function TariffsPage() {
  const { data, reload } = useLoad(() => api.tariffs())
  const [head, setHead] = useState({
    name: '', effective_date: '', day_type: 'workday', note: '',
  })
  const [periods, setPeriods] = useState([emptyPeriod()])
  const [err, setErr] = useState('')
  const [ok, setOk] = useState('')

  const setP = (k, field, v) =>
    setPeriods((ps) => ps.map((p, i) => i === k ? { ...p, [field]: v } : p))

  const submit = async () => {
    setErr(''); setOk('')
    const body = {
      ...head,
      periods: periods.map((p) => ({
        label: p.label,
        start_min: toMin(p.start), end_min: toMin(p.end),
        price_yuan: p.price_yuan,
      })),
    }
    try {
      await api.createTariff(body)
      setOk('电价版本已创建')
      setHead({ name: '', effective_date: '', day_type: 'workday', note: '' })
      setPeriods([emptyPeriod()])
      reload()
    } catch (e) {
      setErr(e.message)
    }
  }

  return (
    <div>
      <div className="card">
        <h2>新建电价版本（时段须无缝覆盖 00:00–24:00）</h2>
        <div className="row">
          <div className="field">
            <label htmlFor="tariff-name">版本名称</label>
            <input id="tariff-name" value={head.name}
              onChange={(e) => setHead({ ...head, name: e.target.value })} />
          </div>
          <div className="field">
            <label htmlFor="tariff-date">生效日期</label>
            <input id="tariff-date" type="date" value={head.effective_date}
              onChange={(e) => setHead({ ...head,
                effective_date: e.target.value })} />
          </div>
          <div className="field">
            <label>日类型</label>
            <select value={head.day_type}
              onChange={(e) => setHead({ ...head, day_type: e.target.value })}>
                <option value="workday">工作日</option>
                <option value="holiday">节假日</option>
              </select>
          </div>
          <div className="field">
            <label>备注</label>
            <input value={head.note}
              onChange={(e) => setHead({ ...head, note: e.target.value })} />
          </div>
        </div>

        <div className="scroll-x" style={{ marginTop: 12 }}>
          <table>
            <thead>
              <tr>
                <th>时段标签</th><th>开始(含)</th><th>结束(不含)</th>
                <th className="num">单价(元/kWh)</th><th></th>
              </tr>
            </thead>
            <tbody>
              {periods.map((p, k) => (
                <tr key={k}>
                  <td>
                    <select value={p.label}
                      onChange={(e) => setP(k, 'label', e.target.value)}>
                      {['谷', '平', '峰', '尖'].map((l) =>
                        <option key={l}>{l}</option>)}
                    </select>
                  </td>
                  <td><input type="time" value={p.start}
                    onChange={(e) => setP(k, 'start', e.target.value)} /></td>
                  <td><input type="time" value={p.end}
                    onChange={(e) => setP(k, 'end', e.target.value)} /></td>
                  <td><input type="number" step="0.0001"
                    value={p.price_yuan}
                    onChange={(e) => setP(k, 'price_yuan', e.target.value)} />
                  </td>
                  <td>
                    <button className="btn danger"
                      disabled={periods.length === 1}
                      onClick={() => setPeriods((ps) =>
                        ps.filter((_, i) => i !== k))}>删除</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="row" style={{ marginTop: 10 }}>
          <button className="btn"
            onClick={() => setPeriods((ps) => [...ps, emptyPeriod()])}>
            增加时段
          </button>
          <button className="btn primary"
            disabled={!head.name || !head.effective_date}
            onClick={submit}>创建版本</button>
        </div>
        {err && <p className="msg-err">{err}</p>}
        {ok && <p className="msg-ok">{ok}</p>}
      </div>

      <div className="card">
        <h2>CSV 导入</h2>
        <CsvUpload templateName="tariffs"
          onUpload={async (f) => { const r = await api.importTariffs(f)
            reload(); return r }} />
      </div>

      <div className="card">
        <h2>已生效版本（{data?.length || 0}）</h2>
        <div className="scroll-x">
          <table>
            <thead>
              <tr>
                <th>生效日期</th><th>日类型</th><th>名称</th>
                <th>时段覆盖</th><th></th>
              </tr>
            </thead>
            <tbody>
              {(data || []).map((t) => (
                <tr key={t.id}>
                  <td className="mono">{t.effective_date}</td>
                  <td>{t.day_type === 'workday' ? '工作日' : '节假日'}</td>
                  <td>{t.name}</td>
                  <td>
                    {t.periods.map((p, k) => (
                      <span key={k} className="badge" style={{
                        marginRight: 6, color: 'var(--text-primary)',
                      }}>
                        <span className="dot"
                          style={{ background: touColor(p.label) }} />
                        {p.label} {p.start_min}-{p.end_min}min
                        ¥{p.price_yuan}
                      </span>
                    ))}
                  </td>
                  <td>
                    <button className="btn danger"
                      onClick={async () => {
                        await api.deleteTariff(t.id); reload()
                      }}>删除</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function toMin(hhmm) {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}
