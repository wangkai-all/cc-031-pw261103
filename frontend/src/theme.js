/** 分时标签 -> 固定槽位色（实体固定，不随数据顺序变化）。 */
export const TOU_COLORS = {
  谷: 'var(--series-1)',
  平: 'var(--series-2)',
  峰: 'var(--series-3)',
  尖: 'var(--series-4)',
}
export const TOU_ORDER = ['谷', '平', '峰', '尖']

export function touColor(label) {
  return TOU_COLORS[label] || 'var(--text-muted)'
}

export function cssVar(name) {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(name).trim()
}

export function isDark() {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

export const FLAG_TEXT = {
  normal: '正常',
  reset: '清零',
  replacement: '换表',
}

export const KIND_TEXT = {
  gap: '缺测',
  break: '断点',
  drop: '读数下降',
  valid: '有效',
}
