import { useCallback, useEffect, useState } from 'react'
import { api } from './api'

export function useLoad(fn, deps = []) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const reload = useCallback(() => {
    setLoading(true)
    Promise.resolve(fn())
      .then((d) => { setData(d); setError('') })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(reload, [reload])
  return { data, error, loading, reload, setData }
}

export function MeterSelect({ meters, value, onChange }) {
  return (
    <select value={value ?? ''}
      onChange={(e) => onChange(Number(e.target.value) || null)}>
      <option value="" disabled>选择电表</option>
      {meters.map((m) => (
        <option key={m.id} value={m.id}>{m.code} · {m.name}</option>
      ))}
    </select>
  )
}

export function CsvUpload({ onUpload, templateName, label = '导入 CSV' }) {
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  return (
    <div>
      <div className="row">
        <label className="btn">
          {label}
          <input type="file" accept=".csv,text/csv" hidden
            onChange={async (e) => {
              const file = e.target.files?.[0]
              if (!file) return
              setMsg(''); setErr('')
              try {
                const out = await onUpload(file)
                const errs = out.errors?.length
                  ? `；${out.errors.length} 条问题：${out.errors.slice(0, 3).join('；')}`
                  : ''
                setMsg(`成功 ${out.inserted} 条${errs}`)
              } catch (ex) {
                setErr(ex.message)
              }
              e.target.value = ''
            }} />
        </label>
        <a className="btn" href={api.template(templateName)}
          download style={{ textDecoration: 'none', display: 'inline-flex',
            alignItems: 'center' }}>
          下载模板
        </a>
      </div>
      {msg && <p className="msg-ok" style={{ marginBottom: 0 }}>{msg}</p>}
      {err && <p className="msg-err" style={{ marginBottom: 0 }}>{err}</p>}
    </div>
  )
}
