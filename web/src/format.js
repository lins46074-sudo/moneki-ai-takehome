/** 数字格式化。看板上的金额、数量都按中文习惯带千分位。 */

const MONEY = new Intl.NumberFormat('zh-CN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const INTEGER = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 })

const NUMBER = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 })

/** ¥1,234.56；没有值时给一个破折号，不要显示 0 冒充真实数据。 */
export function money(value) {
  if (value === null || value === undefined) return '—'
  return `¥${MONEY.format(value)}`
}

export function count(value) {
  if (value === null || value === undefined) return '—'
  return INTEGER.format(value)
}

export function number(value) {
  if (value === null || value === undefined) return '—'
  return NUMBER.format(value)
}

export function percent(value, digits = 2) {
  if (value === null || value === undefined) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

/** 轴刻度用：大数折算成「万」，小数保持原样。 */
export function axisValue(value) {
  const size = Math.abs(value)
  if (size >= 10000) return `${(value / 10000).toFixed(size >= 100000 ? 0 : 1)}万`
  return INTEGER.format(value)
}

/** 主数字下面那行小字用的概数。 */
export function approx(value, unit = '') {
  if (value === null || value === undefined) return ''
  const size = Math.abs(value)
  if (size >= 10000) return `约 ${(value / 10000).toFixed(2)} 万${unit}`
  return `${NUMBER.format(value)}${unit}`
}

/** 日期的中文短写法：2026-06-01 → 6 月 1 日。 */
export function shortDate(iso) {
  if (!iso) return '—'
  const [, month, day] = iso.split('-')
  return `${Number(month)} 月 ${Number(day)} 日`
}
