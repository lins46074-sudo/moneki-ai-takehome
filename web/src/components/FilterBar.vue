<script setup>
/**
 * 筛选行：一行，位于所有内容之上，作用于下面每一张图、每一个数字。
 * 快捷区间按后端的「今天」（契约规定固定为 2026-09-01）算，不按浏览器本机时间，
 * 否则运营在别的时区打开会得到不同的区间。
 */
import { computed } from 'vue'

const props = defineProps({
  meta: { type: Object, required: true },
  filters: { type: Object, required: true },
  refreshing: { type: Boolean, default: false },
})

const emit = defineEmits(['update', 'reset'])

/** 按天位移，用 UTC 计算，避开时区把日期挪掉一天。 */
function shiftDays(iso, delta) {
  const [year, month, day] = iso.split('-').map(Number)
  const moved = new Date(Date.UTC(year, month - 1, day + delta))
  return moved.toISOString().slice(0, 10)
}

function monthRange(iso, offset) {
  const [year, month] = iso.split('-').map(Number)
  const first = new Date(Date.UTC(year, month - 1 + offset, 1))
  // 下个月的第 0 天就是这个月的最后一天
  const last = new Date(Date.UTC(year, month - 1 + offset + 1, 0))
  return [first.toISOString().slice(0, 10), last.toISOString().slice(0, 10)]
}

const presets = computed(() => {
  const today = props.meta.today
  const period = props.meta.data_period || { start: today, end: today }
  return [
    { key: 'all', label: '数据全期', range: [period.start, period.end] },
    { key: '7d', label: '近 7 天', range: [shiftDays(today, -6), today] },
    { key: '30d', label: '近 30 天', range: [shiftDays(today, -29), today] },
    { key: '90d', label: '近 90 天', range: [shiftDays(today, -89), today] },
    { key: 'lastMonth', label: '上月', range: monthRange(today, -1) },
  ]
})

const activePreset = computed(() => {
  const hit = presets.value.find(
    (preset) => preset.range[0] === props.filters.start && preset.range[1] === props.filters.end,
  )
  return hit ? hit.key : ''
})

function usePreset(preset) {
  emit('update', { start: preset.range[0], end: preset.range[1] })
}

function setStart(value) {
  // 起点晚于终点时把终点一起推过去，不给后端送一个空区间。
  const end = value > props.filters.end ? value : props.filters.end
  emit('update', { start: value, end })
}

function setEnd(value) {
  const start = value < props.filters.start ? value : props.filters.start
  emit('update', { end: value, start })
}
</script>

<template>
  <div class="filters">
    <div class="presets" role="group" aria-label="快捷区间">
      <button
        v-for="preset in presets"
        :key="preset.key"
        type="button"
        :aria-pressed="activePreset === preset.key"
        @click="usePreset(preset)"
      >
        {{ preset.label }}
      </button>
    </div>

    <div class="sep" aria-hidden="true"></div>

    <label class="field">
      日期
      <input type="date" :value="filters.start" :max="filters.end" @change="setStart($event.target.value)" />
      <span aria-hidden="true">→</span>
      <input type="date" :value="filters.end" :min="filters.start" @change="setEnd($event.target.value)" />
    </label>

    <div class="sep" aria-hidden="true"></div>

    <label class="field">
      门店
      <select :value="filters.storeId" @change="emit('update', { storeId: $event.target.value })">
        <option value="">全部门店</option>
        <option v-for="store in meta.stores" :key="store.store_id" :value="store.store_id">
          {{ store.store_id }} · {{ store.store_name }}
        </option>
      </select>
    </label>

    <label class="field">
      商品
      <select :value="filters.productId" @change="emit('update', { productId: $event.target.value })">
        <option value="">全部商品</option>
        <option v-for="product in meta.products" :key="product.product_id" :value="product.product_id">
          {{ product.product_name }}
        </option>
      </select>
    </label>

    <span class="spacer"></span>

    <button class="ghost" type="button" @click="emit('reset')">重置</button>
    <span v-if="refreshing" class="hint" role="status">加载中…</span>
  </div>
</template>
