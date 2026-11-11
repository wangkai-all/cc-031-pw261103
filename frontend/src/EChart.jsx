import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import { cssVar, isDark } from './theme'

/** 通用 ECharts 包装：随主题与 option 变化重绘，自适应宽度。 */
export default function EChart({ option, height = 340 }) {
  const ref = useRef(null)
  const chartRef = useRef(null)

  useEffect(() => {
    const chart = echarts.init(ref.current)
    chartRef.current = chart
    const ro = new ResizeObserver(() => chart.resize())
    ro.observe(ref.current)
    const onTheme = () => chart.resize()
    window.matchMedia('(prefers-color-scheme: dark)')
      .addEventListener('change', onTheme)
    return () => {
      ro.disconnect()
      window.matchMedia('(prefers-color-scheme: dark)')
        .removeEventListener('change', onTheme)
      chart.dispose()
    }
  }, [])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart || !option) return
    const text = cssVar('--text-secondary')
    const grid = cssVar('--border')
    chart.setOption({
      backgroundColor: 'transparent',
      textStyle: { color: text, fontFamily: 'inherit' },
      color: [cssVar('--series-1'), cssVar('--series-2'),
        cssVar('--series-3'), cssVar('--series-4')],
      tooltip: {
        trigger: 'axis',
        backgroundColor: cssVar('--surface-2'),
        borderColor: grid,
        textStyle: { color: cssVar('--text-primary') },
      },
      grid: { left: 56, right: 24, top: 36, bottom: 48 },
      ...option,
    }, true)
  }, [option])

  return <div ref={ref} style={{ width: '100%', height }} />
}

export { isDark }
