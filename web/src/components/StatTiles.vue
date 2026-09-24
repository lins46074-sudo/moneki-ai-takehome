<script setup>
/**
 * KPI 行：一整屏只有一个主数字（净营业额），其余是普通指标块。
 * 口径全部来自 KB-001 §4，与 /api/metrics/summary 一致。
 */
import { computed } from 'vue'

import { approx, count, money, number } from '@/format'

const props = defineProps({
  summary: { type: Object, default: null },
  days: { type: Number, default: 0 },
  loading: { type: Boolean, default: false },
})

const tiles = computed(() => {
  const data = props.summary || {}
  return [
    {
      key: 'orders',
      label: '有效订单数',
      value: count(data.orders),
      foot: `${props.days} 天 · 多行订单算 1 单`,
    },
    {
      key: 'aov',
      label: '客单价',
      value: data.aov === null || data.aov === undefined ? '—' : money(data.aov),
      foot: '净营业额 ÷ 有效订单数',
    },
    {
      key: 'qty',
      label: '销量',
      value: count(data.qty),
      foot: '销售数量减退款数量',
    },
    {
      key: 'refund',
      label: '退款金额',
      value: money(data.refund_amount),
      foot: '退款行金额之和',
    },
  ]
})
</script>

<template>
  <section class="kpi-row" :class="{ 'is-refreshing': loading }" aria-label="区间汇总">
    <article class="tile hero">
      <p class="label">净营业额</p>
      <p class="value">{{ money(summary?.net_revenue) }}</p>
      <p class="foot">销售金额 + 退款金额（退款为负，实际是相减）· {{ approx(summary?.net_revenue, ' 元') }}</p>
    </article>
    <article v-for="tile in tiles" :key="tile.key" class="tile">
      <p class="label">{{ tile.label }}</p>
      <p class="value">{{ tile.value }}</p>
      <p class="foot">{{ tile.foot }}</p>
    </article>
  </section>
</template>
