<script setup>
/**
 * 门店对比（横向条形）。
 *
 * 每家门店是名义类别、没有内在顺序，所以所有条用同一个颜色，
 * 不能按金额深浅上色——那会把长度这一个信息重复编码两遍，
 * 还占掉唯一的自由通道。数值直接标在条形末端，不靠悬停才看得到。
 */
import { computed } from 'vue'

import VChart from '@/components/VChart.vue'
import { money } from '@/format'
import { tokens } from '@/theme'

const props = defineProps({
  stores: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})

// 图里从下往上画，所以倒过来让金额最高的排在最上面
const rows = computed(() => [...props.stores].reverse())

const option = computed(() => {
  const tone = tokens.value
  return {
    animationDuration: 280,
    grid: { left: 4, right: 84, top: 6, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'item',
      backgroundColor: tone.surface,
      borderColor: tone.gridline,
      borderWidth: 1,
      padding: [9, 12],
      textStyle: { color: tone.textPrimary, fontSize: 12 },
      formatter: (point) => {
        const store = rows.value[point.dataIndex] || {}
        const escape = (text) =>
          String(text).replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char])
        return (
          `<b style="font-variant-numeric:tabular-nums">${escape(money(store.net_revenue))}</b>` +
          `<div style="color:${tone.textSecondary};font-size:11.5px;margin-top:2px">` +
          `${escape(store.store_id)} · ${escape(store.store_name)} · ${escape(store.category)}</div>` +
          `<div style="color:${tone.textMuted};font-size:11.5px">订单 ${escape(store.orders)} · 销量 ${escape(store.qty)}</div>`
        )
      },
    },
    xAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: tone.gridline, type: 'solid', width: 1 } },
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: tone.textMuted,
        fontSize: 11,
        formatter: (value) => (Math.abs(value) >= 10000 ? `${(value / 10000).toFixed(0)}万` : String(value)),
      },
    },
    yAxis: {
      type: 'category',
      data: rows.value.map((store) => `${store.store_id} ${store.store_name}`),
      axisTick: { show: false },
      // 类目轴默认的竖直分割线会压在网格边缘上，关掉
      splitLine: { show: false },
      axisLine: { lineStyle: { color: tone.axis, width: 1 } },
      axisLabel: { color: tone.textSecondary, fontSize: 11.5 },
    },
    series: [
      {
        name: '净营业额',
        type: 'bar',
        data: rows.value.map((store) => store.net_revenue),
        barMaxWidth: 24,
        // 数据端 4px 圆角，基线端保持方角
        itemStyle: { color: tone.series1, borderRadius: [0, 4, 4, 0] },
        emphasis: { itemStyle: { color: tone.series1, opacity: 0.85 } },
        label: {
          show: true,
          position: 'right',
          distance: 8,
          color: tone.textSecondary,
          fontSize: 11,
          formatter: (point) => money(point.value),
        },
      },
    ],
  }
})

const chartLabel = computed(() =>
  props.stores.length
    ? `各门店净营业额对比，最高为 ${props.stores[0].store_name}`
    : '各门店净营业额对比',
)
</script>

<template>
  <section class="card" :class="{ 'is-refreshing': loading }">
    <header>
      <div>
        <h2>门店对比</h2>
        <p class="hint">净营业额 · 按金额从高到低</p>
      </div>
    </header>
    <VChart :option="option" :height="Math.max(stores.length * 46, 180)" :label="chartLabel" />
  </section>
</template>
