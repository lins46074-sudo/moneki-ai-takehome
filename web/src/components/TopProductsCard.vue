<script setup>
/**
 * Top 商品表。
 *
 * 十来个品类各自带意义时，表格比图表更清楚（颜色分不出十种还能分得清的），
 * 所以这里用表 + 一根占比条：长度编码占比，占比数字本身也写在旁边，
 * 不依赖读者去估条形的长度。
 */
import { computed } from 'vue'

import { count, money, percent } from '@/format'

const props = defineProps({
  products: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  loading: { type: Boolean, default: false },
})

/** 占比条的宽度按最大的一项取满，条形之间才有区分度。 */
const peak = computed(() => Math.max(...props.products.map((item) => item.share || 0), 0.0001))

function widthOf(share) {
  return `${Math.max((share || 0) / peak.value, 0.02) * 100}%`
}

const caption = computed(() => `净营业额前 ${props.products.length} 的商品`)
</script>

<template>
  <section class="card" :class="{ 'is-refreshing': loading }">
    <header>
      <div>
        <h2>商品排行</h2>
        <p class="hint">{{ caption }} · 区间合计 {{ money(total) }}</p>
      </div>
    </header>

    <div class="table-wrap">
      <table>
        <caption class="sr-only">{{ caption }}</caption>
        <thead>
          <tr>
            <th scope="col" style="width: 32px">#</th>
            <th scope="col">商品</th>
            <th scope="col" class="num">净营业额</th>
            <th scope="col" style="min-width: 150px">占区间比</th>
            <th scope="col" class="num">订单数</th>
            <th scope="col" class="num">销量</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in products" :key="item.product_id">
            <td><span class="rank">{{ item.rank }}</span></td>
            <td>
              {{ item.product_name }}
              <span class="hint" style="display: block">{{ item.product_id }} · {{ item.product_category }}</span>
            </td>
            <td class="num">{{ money(item.net_revenue) }}</td>
            <td>
              <div class="meter">
                <span class="track"><span class="fill" :style="{ width: widthOf(item.share) }"></span></span>
                <span class="pct">{{ percent(item.share) }}</span>
              </div>
            </td>
            <td class="num">{{ count(item.orders) }}</td>
            <td class="num">{{ count(item.qty) }}</td>
          </tr>
          <tr v-if="!products.length">
            <td colspan="6" class="hint">这个区间没有销售数据。</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
