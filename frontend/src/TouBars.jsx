import EChart from './EChart'
import { cssVar, touColor, TOU_ORDER } from './theme'

/** 每日分时电量堆叠柱（单轴：kWh）。 */
export function TouEnergyBars({ bills }) {
  const days = bills.map((b) => b.date)
  const labelSet = new Set()
  bills.forEach((b) => (b.tou_items || []).forEach((i) => labelSet.add(i.label)))
  const labels = TOU_ORDER.filter((l) => labelSet.has(l))
  const series = labels.map((label) => ({
    name: label,
    type: 'bar',
    stack: 'energy',
    barMaxWidth: 42,
    itemStyle: { color: touColor(label), borderRadius: [0, 0, 0, 0] },
    emphasis: { focus: 'series' },
    data: bills.map((b) => {
      const item = (b.tou_items || []).find((i) => i.label === label)
      return item ? Number(item.energy_kwh) : 0
    }),
  }))

  return (
    <EChart
      height={300}
      option={{
        legend: { top: 0, textStyle: { color: cssVar('--text-secondary') } },
        xAxis: {
          type: 'category', data: days,
          axisLine: { lineStyle: { color: cssVar('--border') } },
          axisLabel: { color: cssVar('--text-secondary') },
        },
        yAxis: {
          type: 'value', name: 'kWh',
          nameTextStyle: { color: cssVar('--text-muted') },
          splitLine: { lineStyle: { color: cssVar('--border'), type: 'dashed' } },
          axisLabel: { color: cssVar('--text-secondary') },
        },
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'shadow' },
          valueFormatter: (v) => `${Number(v).toFixed(3)} kWh`,
        },
        series,
      }}
    />
  )
}

/** 每日账单费用柱（单轴：元）；blocked 日期不产生费用，不绘制。 */
export function DailyCostBars({ bills }) {
  const ok = bills.filter((b) => b.status === 'ok')
  return (
    <EChart
      height={300}
      option={{
        xAxis: {
          type: 'category',
          data: ok.map((b) => b.date),
          axisLine: { lineStyle: { color: cssVar('--border') } },
          axisLabel: { color: cssVar('--text-secondary') },
        },
        yAxis: {
          type: 'value', name: '元',
          nameTextStyle: { color: cssVar('--text-muted') },
          splitLine: { lineStyle: { color: cssVar('--border'), type: 'dashed' } },
          axisLabel: { color: cssVar('--text-secondary') },
        },
        tooltip: {
          trigger: 'axis',
          axisPointer: { type: 'shadow' },
          valueFormatter: (v) => `¥ ${Number(v).toFixed(2)}`,
        },
        series: [{
          name: '账单总额',
          type: 'bar',
          barMaxWidth: 42,
          data: ok.map((b) => Number(b.total_yuan)),
          itemStyle: {
            color: cssVar('--series-1'),
            borderRadius: [4, 4, 0, 0],
          },
          label: {
            show: true, position: 'top', fontSize: 11,
            color: cssVar('--text-secondary'),
            formatter: (p) => Number(p.value).toFixed(2),
          },
        }],
      }}
    />
  )
}
