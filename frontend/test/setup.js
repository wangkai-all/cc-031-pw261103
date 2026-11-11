import '@testing-library/jest-dom/vitest'
import { vi } from 'vitest'

// 组件中的相对路径 /api 请求转发到本机真实 FastAPI
const realFetch = globalThis.fetch
globalThis.fetch = (input, init) => {
  const url = typeof input === 'string' && input.startsWith('/')
    ? new URL(input, 'http://127.0.0.1:8000')
    : input
  return realFetch(url, init)
}

// jsdom 缺少的浏览器 API 垫片
if (!window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false, media: query, onchange: null,
    addListener: () => {}, removeListener: () => {},
    addEventListener: () => {}, removeEventListener: () => {},
    dispatchEvent: () => false,
  })
}
if (!window.ResizeObserver) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}
if (!window.scrollTo) window.scrollTo = () => {}

// ECharts 在 jsdom 下无法使用 canvas，用可观测桩替换，
// 使组件逻辑（option 计算、点击、数据装配）仍可被端到端验证。
vi.mock('echarts', () => {
  const instances = []
  const init = () => {
    const inst = {
      options: [],
      setOption(opt) { this.options.push(opt) },
      getOption() { return this.options[this.options.length - 1] },
      resize() {},
      dispose() {},
    }
    instances.push(inst)
    return inst
  }
  return { init, _instances: instances }
})
