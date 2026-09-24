<script setup>
/**
 * 营业额趋势（折线）。
 *
 * 只画净营业额一条线：两个量纲不同的指标共用一张图就得配两条 Y 轴，
 * 而双轴的对齐比例是人为定的，会凭空造出并不存在的相关性。要看别的指标，
 * 换到「表」里看，或者用上面的筛选把范围收窄。
 *
 * 折线只直接标注末端一个值，其余交给刻度、十字准星提示和表视图——
 * 每个点都标数字会变成噪音，反而没人读。
 */
import { computed, ref } from 'vue'

import VChart from '@/components/VChart.vue'
import { count, money, number } from '@/format'
import { tokens, withAlpha } from '@/theme'

const props = defineProps({
  days: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})

const view = ref('chart')

/** 提示框内容含后端数据，一律转义后再拼，不直接插字符串。 */
function escapeHtml(text) {
  return String(text).replace(
    /[&<>"']/g,
    (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char],
  )
}

const option = computed(() => {
  const tone = tokens.value
  const dates = props.days.map((day) => day.date)
  const values = props.days.map((day) => day.net_revenue)
  return {
    animationDuration: 280,
    grid: { left: 6, right: 64, top: 20, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: tone.surface,
      borderColor: tone.gridline,
      borderWidth: 1,
      padding: [9, 12],
      textStyle: { color: tone.textPrimary, fontSize: 12 },
      // 十字准星负责找到 X：读者瞄的是某一天，不是那条 2px 的线
      axisPointer: { type: 'line', lineStyle: { color: tone.axis, width: 1 } },
      formatter: (items) => {
        const point = items[0]
        const day = props.days[point.dataIndex] || {}
        const line = (label, value) =>
          `<div style="display:flex;justify-content:space-between;gap:16px;line-height:1.7">
             <span style="color:${tone.textSecondary}">${escapeHtml(label)}</span>
             <b style="font-variant-numeric:tabular-nums">${escapeHtml(value)}</b>
           </div>`
        return (
          `<div style="font-size:11.5px;color:${tone.textMuted};margin-bottom:4px">${escapeHtml(day.date)}</div>` +
          line('净营业额', money(day.net_revenue)) +
          line('有效订单数', count(day.orders)) +
          line('客单价', day.aov === null ? '—' : money(day.aov)) +
          line('销量', count(day.qty))
        )
      },
    },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: false,
      axisTick: { show: false },
      // 类目轴默认会画一条竖直的分割线，正好压在网格左边缘上，是多余的墨迹
      splitLine: { show: false },
      axisLine: { lineStyle: { color: tone.axis, width: 1 } },
      axisLabel: { color: tone.textMuted, fontSize: 11, hideOverlap: true },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: tone.gridline, type: 'solid', width: 1 } },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: tone.textMuted,
        fontSize: 11,
        formatter: (value) => (Math.abs(value) >= 10000 ? `${(value / 10000).toFixed(1)}万` : String(value)),
      },
    },
    series: [
      {
        name: '净营业额',
        type: 'line',
        data: values,
        // 2px 线、圆角接头；数据点默认不画，悬停时才出现
        lineStyle: { width: 2, color: tone.series1, cap: 'round', join: 'round' },
        itemStyle: { color: tone.series1, borderColor: tone.surface, borderWidth: 2 },
        symbol: 'circle',
        symbolSize: 8,
        showSymbol: false,
        emphasis: { focus: 'series', scale: 1.15 },
        // 面积填充只是一层 10% 上下的薄雾，不是实心色块
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: withAlpha(tone.series1, 0.16) },
              { offset: 1, color: withAlpha(tone.series1, 0) },
            ],
          },
        },
        // 只标末端一个值，作为「图上直接看得到数」的锚点
        endLabel: {
          show: true,
          color: tone.textSecondary,
          fontSize: 11,
          formatter: (point) => (point.value == null ? '' : number(point.value)),
        },
      },
    ],
  }
})

const chartLabel = computed(
  () => `净营业额折线图，共 ${props.days.length} 天，从 ${props.days[0]?.date || '—'} 到 ${props.days.at(-1)?.date || '—'}`,
)
</script>

<template>
  <section class="card" :class="{ 'is-refreshing': loading }">
    <header>
      <div>
        <h2>营业额趋势</h2>
        <p class="hint">按天净营业额 · 共 {{ days.length }} 天 · 退款行按退款当天归属</p>
      </div>
      <div class="segmented" role="group" aria-label="视图切换">
        <button type="button" :aria-pressed="view === 'chart'" @click="view = 'chart'">图</button>
        <button type="button" :aria-pressed="view === 'table'" @click="view = 'table'">表</button>
      </div>
    </header>

    <VChart v-if="view === 'chart'" :option="option" :height="288" :label="chartLabel" />

    <div v-else class="table-wrap" style="max-height: 300px; overflow-y: auto">
      <table>
        <caption class="sr-only">按天净营业额明细</caption>
        <thead>
          <tr>
            <th scope="col">日期</th>
            <th scope="col" class="num">净营业额</th>
            <th scope="col" class="num">退款金额</th>
            <th scope="col" class="num">有效订单数</th>
            <th scope="col" class="num">客单价</th>
            <th scope="col" class="num">销量</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="day in days" :key="day.date">
            <td>{{ day.date }}</td>
            <td class="num">{{ money(day.net_revenue) }}</td>
            <td class="num">{{ money(day.refund_amount) }}</td>
            <td class="num">{{ count(day.orders) }}</td>
            <td class="num">{{ day.aov === null ? '—' : money(day.aov) }}</td>
            <td class="num">{{ count(day.qty) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
