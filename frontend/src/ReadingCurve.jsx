import EChart from './EChart'
import { cssVar, touColor } from './theme'

/**
 * 累计读数曲线：折线展示累计读数；换表/清零点用状态色标记，
 * 缺测/下降/断点区间用 markArea 背景带标出（颜色不单独承载含义，
 * 另有待核查表格与图例文字）。
 */
export default function ReadingCurve({ readings, anomalies }) {
  const points = readings.map((r) => [r.read_at, Number(r.reading_kwh)])
  const flagged = readings
    .filter((r) => r.flag !== 'normal')
    .map((r) => ({
      name: r.flag === 'replacement' ? '换表' : '清零',
      coord: [r.read_at, Number(r.reading_kwh)],
      itemStyle: { color: cssVar('--status-danger') },
      label: { show: true, formatter: r.flag === 'replacement' ? '换表' : '清零',
        color: cssVar('--status-danger'), position: 'top', fontSize: 11 },
    }))

  const areaColor = {
    gap: cssVar('--status-warn'),
    drop: cssVar('--status-warn'),
    break: cssVar('--status-danger'),
  }
  const markAreas = (anomalies || []).map((a) => [
    {
      name: { gap: '缺测', drop: '读数下降', break: '断点' }[a.kind],
      xAxis: a.start_read_at,
      itemStyle: {
        color: areaColor[a.kind],
        opacity: 0.12,
        borderColor: areaColor[a.kind],
        borderWidth: 1,
        borderType: 'dashed',
      },
    },
    { xAxis: a.end_read_at },
  ])

  const option = {
    legend: {
      top: 0,
      data: ['累计读数', '换表/清零点', '缺测区间', '断点区间'],
      textStyle: { color: cssVar('--text-secondary') },
    },
    xAxis: {
      type: 'time',
      axisLine: { lineStyle: { color: cssVar('--border') } },
      axisLabel: { color: cssVar('--text-secondary') },
    },
    yAxis: {
      type: 'value',
      name: 'kWh',
      nameTextStyle: { color: cssVar('--text-muted') },
      splitLine: { lineStyle: { color: cssVar('--border'), type: 'dashed' } },
      axisLabel: { color: cssVar('--text-secondary') },
    },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v) => (v == null ? '-' : `${Number(v).toFixed(3)} kWh`),
    },
    series: [
      {
        name: '累计读数',
        type: 'line',
        data: points,
        showSymbol: true,
        symbolSize: 6,
        lineStyle: { width: 2, color: cssVar('--series-1') },
        itemStyle: { color: cssVar('--series-1') },
        markPoint: {
          symbol: 'diamond',
          symbolSize: 14,
          data: flagged,
        },
        markArea: {
          data: markAreas,
          label: {
            show: true,
            position: 'top',
            fontSize: 11,
            color: cssVar('--text-secondary'),
            formatter: (p) => p.data[0].name,
          },
        },
      },
      // 图例占位（异常带通过 markArea 渲染）
      {
        name: '换表/清零点', type: 'scatter', data: [],
        itemStyle: { color: cssVar('--status-danger') },
      },
      {
        name: '缺测区间', type: 'scatter', data: [],
        itemStyle: { color: cssVar('--status-warn'), opacity: 0.5 },
      },
      {
        name: '断点区间', type: 'scatter', data: [],
        itemStyle: { color: cssVar('--status-danger'), opacity: 0.5 },
      },
    ],
  }
  return <EChart option={option} height={380} />
}

export { touColor }
