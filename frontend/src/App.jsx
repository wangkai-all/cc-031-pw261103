import { useState } from 'react'
import { api } from './api'
import { useLoad } from './shared'
import BillingPage from './BillingPage'
import ReadingsPage from './ReadingsPage'
import TariffsPage from './TariffsPage'
import HolidaysPage from './HolidaysPage'

const TABS = [
  ['billing', '账单与核算'],
  ['readings', '读数管理'],
  ['tariffs', '电价规则'],
  ['holidays', '节假日日历'],
]

export default function App() {
  const [tab, setTab] = useState('billing')
  const [meterId, setMeterId] = useState(null)
  const [newCode, setNewCode] = useState('')
  const [newName, setNewName] = useState('')
  const [meterErr, setMeterErr] = useState('')
  const { data: meters, reload: reloadMeters } = useLoad(() => api.meters())

  const createMeter = async () => {
    setMeterErr('')
    try {
      const m = await api.createMeter({ code: newCode, name: newName })
      setNewCode(''); setNewName('')
      await reloadMeters()
      setMeterId(m.id)
    } catch (e) {
      setMeterErr(e.message)
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <h1>分时电量核算平台</h1>
        <div className="tabs">
          {TABS.map(([k, label]) => (
            <button key={k} className={tab === k ? 'active' : ''}
              onClick={() => setTab(k)}>{label}</button>
          ))}
        </div>
      </header>

      <div className="card">
        <div className="row">
          <select value={meterId ?? ''}
            onChange={(e) => setMeterId(Number(e.target.value) || null)}>
            <option value="" disabled>选择电表</option>
            {(meters || []).map((m) =>
              <option key={m.id} value={m.id}>{m.code} · {m.name}</option>)}
          </select>
          <input placeholder="新电表编码" value={newCode}
            onChange={(e) => setNewCode(e.target.value)} />
          <input placeholder="新电表名称" value={newName}
            onChange={(e) => setNewName(e.target.value)} />
          <button className="btn primary"
            disabled={!newCode || !newName}
            onClick={createMeter}>新建电表</button>
          {meterErr && <span className="msg-err">{meterErr}</span>}
        </div>
      </div>

      {tab === 'billing' && (
        <BillingPage meters={meters || []} meterId={meterId}
          setMeterId={setMeterId} />
      )}
      {tab === 'readings' && (
        <ReadingsPage meters={meters || []} meterId={meterId}
          setMeterId={setMeterId} />
      )}
      {tab === 'tariffs' && <TariffsPage />}
      {tab === 'holidays' && <HolidaysPage />}
    </div>
  )
}
