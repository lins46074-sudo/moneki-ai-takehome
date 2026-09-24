<script setup>
/**
 * ECharts 的薄封装：负责实例生命周期、容器尺寸变化和主题切换后的重画。
 * 按需注册组件，避免把整个 ECharts 打进产物。
 */
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

echarts.use([LineChart, BarChart, GridComponent, TooltipComponent, CanvasRenderer])

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: Number, default: 280 },
  /** 给读屏软件的说明：图表画的是什么。 */
  label: { type: String, default: '' },
})

const host = ref(null)
let chart = null
let observer = null

function draw() {
  if (!chart) return
  // notMerge：主题或数据换掉时整份重画，不留上一份的系列。
  chart.setOption(props.option, true)
}

onMounted(() => {
  chart = echarts.init(host.value, null, { renderer: 'canvas' })
  draw()
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(host.value)
})

watch(() => props.option, draw, { deep: true })

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div ref="host" class="chart" :style="{ height: `${height}px` }" role="img" :aria-label="label"></div>
</template>

<style scoped>
.chart {
  width: 100%;
}
</style>
