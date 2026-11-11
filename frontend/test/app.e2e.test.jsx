import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from '../src/App'

const API = 'http://127.0.0.1:8000'
const j = (r) => r.json()

async function api(path, body) {
  const res = await fetch(API + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json()
}

let meter

beforeAll(async () => {
  const stamp = Date.now()
  meter = await api('/api/meters', { code: `E2E-${stamp}`, name: '端到端表' })
  // 有效跨午夜区间（30 分钟，6 度均匀，各 15 分钟 3 度）
  await api(`/api/meters/${meter.id}/readings`, {
    read_at: '2026-11-05 23:45:00', reading_kwh: '100', flag: 'normal' })
  await api(`/api/meters/${meter.id}/readings`, {
    read_at: '2026-11-06 00:15:00', reading_kwh: '106', flag: 'normal' })
  // 缺测（间隔 60 分钟）
  await api(`/api/meters/${meter.id}/readings`, {
    read_at: '2026-11-06 01:15:00', reading_kwh: '110', flag: 'normal' })
  // 无标记下降
  await api(`/api/meters/${meter.id}/readings`, {
    read_at: '2026-11-06 01:45:00', reading_kwh: '108', flag: 'normal' })
  // 换表断点
  await api(`/api/meters/${meter.id}/readings`, {
    read_at: '2026-11-06 02:15:00', reading_kwh: '0',
    flag: 'replacement', note: '换新表' })
  // 新表有效区间
  await api(`/api/meters/${meter.id}/readings`, {
    read_at: '2026-11-06 02:45:00', reading_kwh: '2', flag: 'normal' })
}, 30000)

afterAll(() => document.body.innerHTML = '')

async function renderAndPickMeter() {
  render(<App />)
  // 等待电表列表加载并选中本测试电表
  const select = await screen.findByRole('combobox')
  await waitFor(() =>
    expect(within(select).getByText(new RegExp(meter.code))).toBeInTheDocument())
  await userEvent.selectOptions(select, String(meter.id))
}

describe('账单与核算页', () => {
  it('渲染账单、统计与待核查，未知区间单列', async () => {
    await renderAndPickMeter()

    // 统计卡片
    expect(await screen.findByText('待核查区间')).toBeInTheDocument()
    expect(screen.getByText(/账单天数/)).toBeInTheDocument()

    // 两天账单卡片
    await screen.findByText('2026-11-05')
    const day6 = await screen.findByText('2026-11-06')
    expect(day6).toBeInTheDocument()

    // 待核查三类（缺测/下降/换表）均出现，且标记为未知
    expect(await screen.findByText('缺测')).toBeInTheDocument()
    expect(screen.getByText('读数下降')).toBeInTheDocument()
    expect(screen.getByText('断点')).toBeInTheDocument()
    expect(screen.getByText(/电量未知、不计入上表/)).toBeInTheDocument()

    // 均匀耗电假设出现在页面
    expect(screen.getAllByText(/均匀耗电假设/).length).toBeGreaterThan(0)
  }, 30000)

  it('点击费用链接打开明细弹窗，含两端读数、单价与公式', async () => {
    await renderAndPickMeter()
    const detailBtn = await screen.findAllByRole('button', { name: '查看明细' })
    await userEvent.click(detailBtn[0])

    // 展开的分时段明细表中，费用链接才会打开弹窗
    const segFee = await screen.findAllByText(/^\d+\.\d+$/)
    const modalTrigger = segFee.find(
      (el) => el.classList.contains('fee-link')
        && el.closest('table')?.textContent.includes('拆分时段'))
    expect(modalTrigger).toBeTruthy()
    await userEvent.click(modalTrigger)

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/费用计算明细/)).toBeInTheDocument()
    expect(within(dialog).getByText('起点读数')).toBeInTheDocument()
    expect(within(dialog).getByText('终点读数')).toBeInTheDocument()
    expect(within(dialog).getByText(/单价/)).toBeInTheDocument()
    expect(within(dialog).getByText(/公式/)).toBeInTheDocument()
    expect(within(dialog).getByText(/ROUND_HALF_UP/)).toBeInTheDocument()

    await userEvent.click(within(dialog).getByRole('button', { name: '关闭' }))
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  }, 30000)

  it('跨午夜拆分电量守恒：5 日 3 度、6 日计费 5 度，未知单列', async () => {
    const data = await fetch(
      `${API}/api/meters/${meter.id}/bills`).then(j)
    const byDate = Object.fromEntries(data.bills.map((b) => [b.date, b]))
    expect(byDate['2026-11-05'].energy_kwh).toBe('3.000000')
    // 6 日：跨午夜余下 3 度（缺测/下降/换表均未知）+ 新表 2 度 = 5
    expect(byDate['2026-11-06'].energy_kwh).toBe('5.000000')
    // 段电量之和严格等于账单电量（前端直接展示后端守恒结果）
    for (const bill of data.bills) {
      if (bill.status !== 'ok') continue
      const sum = bill.segments.reduce(
        (s, x) => s + Number(x.energy_kwh), 0)
      expect(sum).toBeCloseTo(Number(bill.energy_kwh), 6)
    }
    // 未知区间绝无电量数字
    for (const u of byDate['2026-11-06'].unknown_intervals) {
      expect(u.energy_kwh).toBeNull()
    }
  }, 15000)
})

describe('电价规则页', () => {
  it('未覆盖全天的时段给出校验错误', async () => {
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: '电价规则' }))
    const heading = await screen.findByText(/新建电价版本/)
    const card = heading.closest('.card')
    // 版本名称
    await userEvent.type(
      within(card).getByRole('textbox', { name: '版本名称' }), '非法版本')
    // 生效日期（卡片内唯一 type=date 且为空的输入）
    fireEvent.change(within(card).getByLabelText('生效日期'),
      { target: { value: '2027-01-01' } })
    // 默认只有一个 00:00-08:00 时段，未覆盖全天
    await userEvent.click(
      within(card).getByRole('button', { name: '创建版本' }))
    await waitFor(() =>
      expect(screen.getByText(/未覆盖全天|缺口/)).toBeInTheDocument())
  }, 30000)
})

describe('节假日日历页', () => {
  it('登记调休补班后列表出现该日期', async () => {
    render(<App />)
    await userEvent.click(screen.getByRole('button', { name: '节假日日历' }))
    const heading = await screen.findByText(/节假日 \/ 调休日历/)
    const card = heading.closest('.card')
    fireEvent.change(await within(card).findByLabelText('日期'),
      { target: { value: '2027-05-08' } })
    await userEvent.selectOptions(within(card).getByRole('combobox'), 'workday')
    await userEvent.click(
      within(card).getByRole('button', { name: '登记' }))
    expect(await screen.findByText('2027-05-08')).toBeInTheDocument()
    // 已登记表格（区别于下拉框 option）中的调休补班徽章
    const rows = screen.getAllByText('调休补班')
    expect(rows.some((el) => el.classList.contains('badge'))).toBe(true)
  }, 30000)
})
