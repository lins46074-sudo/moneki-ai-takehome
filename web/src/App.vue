<script setup>
/**
 * 经营看板。
 *
 * 一个筛选行管住下面所有内容：改一次筛选，四张卡片一起重算，
 * 所以屏幕上的数字永远属于同一个切片。
 */
import { computed, onMounted, ref } from 'vue'

import { api, sliceParams } from '@/api'
import ChatCard from '@/components/ChatCard.vue'
import DataQualityCard from '@/components/DataQualityCard.vue'
import FilterBar from '@/components/FilterBar.vue'
import StatTiles from '@/components/StatTiles.vue'
import StoreCompareCard from '@/components/StoreCompareCard.vue'
import TopProductsCard from '@/components/TopProductsCard.vue'
import TrendCard from '@/components/TrendCard.vue'
import { count } from '@/format'
import { applyTheme, followSystemTheme, theme } from '@/theme'

const meta = ref(null)
const quality = ref(null)
const summary = ref(null)
const days = ref([])
const products = ref([])
const productTotal = ref(0)
const stores = ref([])
const booting = ref(true)
const refreshing = ref(false)
const error = ref('')

const filters = ref({ start: '', end: '', storeId: '', productId: '' })

// 连点筛选时，先发的请求可能后回来。用一个自增令牌丢弃过期结果，
// 避免旧数据盖住新数据。
let requestToken = 0

const sliceLabel = computed(() => {
  if (!filters.value.start) return ''
  const store = filters.value.storeId || '全部门店'
  const product = filters.value.productId || '全部商品'
  return `${filters.value.start} 至 ${filters.value.end} · ${store} · ${product}`
})

async function loadMetrics() {
  const token = ++requestToken
  refreshing.value = true
  error.value = ''
  try {
    const params = sliceParams(filters.value)
    const [summaryData, dailyData, topData, storeData] = await Promise.all([
      api.summary(params),
      api.daily(params),
      api.topProducts({ ...params, limit: 10 }),
      api.byStore(params),
    ])
    if (token !== requestToken) return
    summary.value = summaryData
    days.value = dailyData.days
    products.value = topData.products
    productTotal.value = topData.total_net_revenue
    stores.value = storeData.stores
  } catch (problem) {
    if (token !== requestToken) return
    // 保留上一帧数据，只把错误说出来，不清屏
    error.value = problem.message
  } finally {
    if (token === requestToken) refreshing.value = false
  }
}

async function loadShell() {
  booting.value = true
  error.value = ''
  try {
    const [metaData, qualityData] = await Promise.all([api.meta(), api.dataQuality()])
    meta.value = metaData
    quality.value = qualityData
    filters.value = {
      start: metaData.data_period.start,
      end: metaData.data_period.end,
      storeId: '',
      productId: '',
    }
    await loadMetrics()
  } catch (problem) {
    error.value = problem.message
  } finally {
    booting.value = false
  }
}

function updateFilters(patch) {
  filters.value = { ...filters.value, ...patch }
  loadMetrics()
}

function resetFilters() {
  updateFilters({ storeId: '', productId: '', start: meta.value.data_period.start, end: meta.value.data_period.end })
}

onMounted(() => {
  followSystemTheme()
  loadShell()
})
</script>

<template>
  <div class="shell">
    <header class="masthead">
      <div>
        <h1>经营看板</h1>
        <p class="subtitle">
          <template v-if="meta">
            系统的“今天”是 <code>{{ meta.today }}</code> · 数据范围 {{ meta.data_period.start }} 至
            {{ meta.data_period.end }} · 当前切片 {{ sliceLabel }}
          </template>
          <template v-else>正在读取数据…</template>
        </p>
      </div>
      <button class="ghost" type="button" @click="applyTheme(theme === 'dark' ? 'light' : 'dark')">
        {{ theme === 'dark' ? '浅色' : '深色' }}主题
      </button>
    </header>

    <p v-if="error" class="notice error" role="alert">
      没取到数据：{{ error }}
      <button class="ghost" type="button" style="margin-left: 10px" @click="loadShell">重试</button>
    </p>

    <template v-if="meta">
      <FilterBar
        :meta="meta"
        :filters="filters"
        :refreshing="refreshing"
        @update="updateFilters"
        @reset="resetFilters"
      />

      <StatTiles :summary="summary" :days="days.length" :loading="refreshing" />

      <!-- 对话框放在 KPI 之后：运营第一眼看到的是数字，要问的时候它就在下面 -->
      <ChatCard />

      <div class="grid two">
        <TrendCard :days="days" :loading="refreshing" />
        <StoreCompareCard :stores="stores" :loading="refreshing" />
      </div>

      <div class="grid two">
        <TopProductsCard :products="products" :total="productTotal" :loading="refreshing" />
        <DataQualityCard :quality="quality" :loading="refreshing" />
      </div>

      <p class="hint" style="margin-top: 18px">
        指标口径以知识库《指标口径手册 v3》（KB-001）为准：净营业额含退款、有效订单数按不同订单号统计、
        退款行按退款当天归属。共 {{ count(stores.length) }} 家门店参与对比。
      </p>
    </template>

    <p v-else-if="booting" class="notice" role="status">正在加载看板…</p>
  </div>
</template>
