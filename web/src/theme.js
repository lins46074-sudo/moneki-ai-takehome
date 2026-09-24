/**
 * 主题与图表配色。
 *
 * 颜色的唯一来源是 styles.css 里的设计令牌：ECharts 拿不到 CSS 变量，
 * 所以在渲染前把它们读出来。切换主题时重读一次，图表跟着重画。
 */

import { ref } from 'vue'

const STORAGE_KEY = 'moneki-theme'

function systemPrefersDark() {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
}

function readTokens() {
  const styles = getComputedStyle(document.documentElement)
  const read = (name) => styles.getPropertyValue(name).trim()
  return {
    surface: read('--surface-1'),
    gridline: read('--gridline'),
    axis: read('--axis'),
    textPrimary: read('--text-primary'),
    textSecondary: read('--text-secondary'),
    textMuted: read('--text-muted'),
    series1: read('--series-1'),
    series2: read('--series-2'),
  }
}

export const theme = ref(document.documentElement.dataset.theme || 'light')
export const tokens = ref(readTokens())

/** 把主题写到 <html data-theme>，等浏览器应用之后再重读颜色。 */
export function applyTheme(next) {
  document.documentElement.dataset.theme = next
  try {
    localStorage.setItem(STORAGE_KEY, next)
  } catch (error) {
    /* 隐私模式下写不了，忽略：主题只在本次会话有效 */
  }
  theme.value = next
  // 颜色要在新一轮绘制之后才读得到新值。
  window.requestAnimationFrame(() => {
    tokens.value = readTokens()
  })
}

export function toggleTheme() {
  applyTheme(theme.value === 'dark' ? 'light' : 'dark')
}

/** 用户没手动选过主题时，跟着系统设置走。 */
export function followSystemTheme() {
  const media = window.matchMedia?.('(prefers-color-scheme: dark)')
  if (!media) return
  media.addEventListener('change', (event) => {
    let saved = null
    try {
      saved = localStorage.getItem(STORAGE_KEY)
    } catch (error) {
      saved = null
    }
    if (!saved) applyTheme(event.matches ? 'dark' : 'light')
  })
}

export { systemPrefersDark }

/** #2a78d6 + 0.14 → rgba(42,120,214,0.14)，用于面积填充这类半透明色。 */
export function withAlpha(hex, alpha) {
  const text = (hex || '').replace('#', '')
  if (text.length !== 6) return hex
  const value = Number.parseInt(text, 16)
  const red = (value >> 16) & 255
  const green = (value >> 8) & 255
  const blue = value & 255
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`
}
