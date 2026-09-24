<script setup>
/**
 * 数据质量面板：清洗掉了多少行、各因为什么。
 *
 * 左半边是「丢掉的」，右半边是「修好的」——这两件事必须分开讲：
 * 丢掉的 338 行不在任何数字里，而修好的 272 行仍在参与统计。
 * 剔除原因的顺序就是 KB-001 §3 的执行顺序，后端已经排好，这里照着渲染。
 */
import { computed } from 'vue'

import { count, percent } from '@/format'

const props = defineProps({
  quality: { type: Object, default: null },
  loading: { type: Boolean, default: false },
})

const report = computed(() => props.quality?.cleaning_report || {})
const breakdown = computed(() => props.quality?.removal_breakdown || [])
const recovered = computed(() => props.quality?.recovered_breakdown || [])
const warnings = computed(() => props.quality?.kb_warnings || [])

const rawRows = computed(() => report.value.raw_rows || 0)
const keptRows = computed(() => report.value.kept_rows || 0)
const removedRows = computed(() => report.value.removed?.total || 0)
const keptRate = computed(() => (rawRows.value ? keptRows.value / rawRows.value : null))

// 条形宽度按最大的一条取满，小项才看得见
const peak = computed(() => Math.max(...breakdown.value.map((item) => item.rows), 1))

function widthOf(rows) {
  return `${Math.max(rows / peak.value, 0.015) * 100}%`
}
</script>

<template>
  <section class="card" :class="{ 'is-refreshing': loading }">
    <header>
      <div>
        <h2>数据质量</h2>
        <p class="hint">
          按 KB-001 现行口径清洗 · 数据范围
          {{ quality?.data_period?.start }} 至 {{ quality?.data_period?.end }}
        </p>
      </div>
      <span class="hint">
        {{ report.balanced ? '台账已对平' : '台账未对平' }}：原始 = 保留 + 剔除
      </span>
    </header>

    <div class="quality-summary">
      <div>
        <p class="hint">原始明细</p>
        <p class="quality-number">{{ count(rawRows) }}</p>
      </div>
      <span class="quality-arrow" aria-hidden="true">→</span>
      <div>
        <p class="hint">清洗后保留</p>
        <p class="quality-number">{{ count(keptRows) }}</p>
      </div>
      <div>
        <p class="hint">剔除</p>
        <p class="quality-number">{{ count(removedRows) }}</p>
      </div>
      <div>
        <p class="hint">保留率</p>
        <p class="quality-number">{{ percent(keptRate) }}</p>
      </div>
    </div>
    <p class="hint" style="margin-top: 8px">
      保留的 {{ count(keptRows) }} 行里，销售行 {{ count(report.kept_sales_rows) }} 行、退款行
      {{ count(report.kept_refund_rows) }} 行。
    </p>

    <h3 class="section-title">剔除原因（共 {{ count(removedRows) }} 行）</h3>
    <ul class="reason-list">
      <li v-for="item in breakdown" :key="item.reason" class="reason">
        <span class="name" :title="item.reason">{{ item.label }}</span>
        <span class="count">{{ count(item.rows) }} 行</span>
        <span class="bar"><i :style="{ width: widthOf(item.rows) }"></i></span>
      </li>
    </ul>

    <h3 class="section-title">修正后仍在统计的脏写法（共 {{ count(recovered.reduce((sum, item) => sum + item.rows, 0)) }} 行）</h3>
    <div class="recovered">
      <div v-for="item in recovered" :key="item.reason" class="row">
        <span>{{ item.label }}</span>
        <b>{{ count(item.rows) }} 行</b>
      </div>
      <p class="hint" style="margin: 4px 0 0">
        这些行没有丢掉，只是把 <code>¥38.00</code>、<code>s01</code>、<code>2026/6/1</code>
        这类写法规范化之后继续参与统计。
      </p>
    </div>

    <template v-if="warnings.length">
      <h3 class="section-title">知识库告警（{{ warnings.length }} 条）</h3>
      <p class="hint">{{ warnings[0] }}</p>
    </template>
  </section>
</template>

<style scoped>
.quality-summary {
  display: flex;
  align-items: flex-end;
  gap: 14px;
  flex-wrap: wrap;
  padding: 12px 14px;
  background: var(--surface-2);
  border-radius: 12px;
}

.quality-summary > div {
  min-width: 76px;
}

.quality-number {
  margin: 2px 0 0;
  font-size: 20px;
  font-weight: 620;
  font-variant-numeric: tabular-nums;
}

.quality-arrow {
  color: var(--text-muted);
  font-size: 16px;
  padding-bottom: 3px;
}

.section-title {
  margin: 20px 0 10px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  letter-spacing: 0.3px;
}
</style>
