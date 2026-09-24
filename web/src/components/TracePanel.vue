<script setup>
/**
 * 调试面板：把 `GET /api/trace/{trace_id}` 可视化（契约 §6）。
 *
 * 一次回答答错了，看这个面板就该知道错在哪一层：
 * 意图判错了（plan）？该检索的文档没检索到、或者被元数据过滤挡了（search）？
 * 取数取错了（evidence）？还是模型那一侧的问题（llm_calls）？
 *
 * 面板只读，不做任何判断——它把后端记下来的东西原样摊开，
 * 包括「哪些片段被过滤、为什么」和「每一步花了多久」这些平时看不到的中间状态。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { api } from '@/api'

const props = defineProps({
  traceId: { type: String, required: true },
})
const emit = defineEmits(['close'])

const trace = ref(null)
const loading = ref(true)
const error = ref('')
const closeButton = ref(null)

onMounted(async () => {
  try {
    trace.value = await api.trace(props.traceId)
  } catch (problem) {
    // 后端只留最近 200 条，太久以前的会取不到（契约 §6 约定取不到按不合格处理，
    // 这里如实说出来，而不是装作面板是空的）。
    error.value = `取不到这条 trace：${problem.message}`
  } finally {
    loading.value = false
    closeButton.value?.focus()
  }
})

function onKeydown(event) {
  if (event.key === 'Escape') emit('close')
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))

const steps = computed(() => trace.value?.steps || [])
const longestStep = computed(() => Math.max(...steps.value.map((s) => s.took_ms || 0), 1))

const searchStep = computed(() => steps.value.find((step) => step.step === 'search')?.detail || null)
const planStep = computed(() => steps.value.find((step) => step.step === 'plan')?.detail || null)
const evidenceStep = computed(
  () => steps.value.find((step) => step.step === 'evidence')?.detail || null,
)

const hits = computed(() => searchStep.value?.hits || [])
const topScore = computed(() => Math.max(...hits.value.map((hit) => hit.score || 0), 0.0001))

const STEP_LABELS = {
  plan: '理解问题',
  search: '检索',
  answer_mock: '组织回答（降级模式）',
  answer_live: '组织回答（模型）',
  answer_live_failed: '模型调用失败',
  evidence: '证据与引用',
  response: '返回',
}

function barWidth(value, peak) {
  return `${Math.max((value || 0) / peak, 0.01) * 100}%`
}

function pretty(value) {
  try {
    return JSON.stringify(value, null, 1)
  } catch (problem) {
    return String(value)
  }
}

/** 检索用的查询与原始问题不一样时，说明做过改写，值得单独指出来。 */
const rewritten = computed(() => {
  const query = searchStep.value?.query || ''
  const question = trace.value?.question || ''
  return query && query !== question ? query : ''
})
</script>

<template>
  <div class="overlay" role="dialog" aria-modal="true" aria-label="这次回答的处理过程" @click.self="emit('close')">
    <div class="panel">
      <header class="panel-head">
        <div>
          <h2>处理过程</h2>
          <p class="hint">
            <code>{{ traceId }}</code>
            <template v-if="trace"> · 共 {{ trace.total_ms }} ms</template>
          </p>
        </div>
        <button ref="closeButton" class="ghost" type="button" @click="emit('close')">关闭</button>
      </header>

      <div class="panel-body">
        <p v-if="loading" class="hint">正在读取…</p>
        <p v-else-if="error" class="notice error" role="alert">{{ error }}</p>

        <template v-else>
          <section>
            <h3>问题</h3>
            <p class="mono-block">{{ trace.question }}</p>
          </section>

          <!-- 每一步的耗时：一眼看出时间花在哪一层 -->
          <section>
            <h3>步骤与耗时</h3>
            <ul class="timeline">
              <li v-for="step in steps" :key="step.step + step.at_ms">
                <span class="step-name">{{ STEP_LABELS[step.step] || step.step }}</span>
                <span class="step-bar">
                  <i :style="{ width: barWidth(step.took_ms, longestStep) }"></i>
                </span>
                <span class="step-time">
                  {{ step.took_ms === null ? '—' : `${step.took_ms} ms` }}
                </span>
              </li>
            </ul>
          </section>

          <!-- 意图：判错了就是整题错，所以放在最前面 -->
          <section v-if="planStep">
            <h3>理解问题</h3>
            <dl class="facts">
              <div><dt>意图</dt><dd>{{ planStep.intent }} / {{ planStep.kind }}</dd></div>
              <div><dt>时间区间</dt><dd>{{ (planStep.window || []).join(' 至 ') || '未指定' }}</dd></div>
              <div><dt>门店 / 商品</dt><dd>{{ planStep.store_id || '全部' }} / {{ planStep.product_id || '全部' }}</dd></div>
              <div><dt>指标</dt><dd>{{ planStep.metric }}</dd></div>
              <div><dt>需要数据库 / 文档</dt><dd>{{ planStep.needs_data ? '是' : '否' }} / {{ planStep.needs_docs ? '是' : '否' }}</dd></div>
            </dl>
            <p v-for="(note, index) in planStep.notes || []" :key="index" class="hint">· {{ note }}</p>
          </section>

          <!-- 检索：命中了什么、多少分、哪些被挡掉 -->
          <section v-if="searchStep">
            <h3>检索</h3>
            <template v-if="rewritten">
              <p class="hint">改写后的检索查询</p>
              <p class="mono-block">{{ rewritten }}</p>
            </template>
            <p v-if="searchStep.expansions && searchStep.expansions.length" class="hint">
              别名扩写：{{ [...new Set(searchStep.expansions)].join('、') }}
            </p>
            <p class="hint">查询覆盖率 {{ searchStep.coverage }}</p>

            <table class="mini">
              <caption class="sr-only">命中的片段与分数</caption>
              <thead>
                <tr>
                  <th scope="col">文档</th>
                  <th scope="col">片段</th>
                  <th scope="col">分数</th>
                  <th scope="col">备注</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="hit in hits" :key="hit.chunk_id">
                  <td>{{ hit.doc_id }}</td>
                  <td>{{ hit.chunk_id }}</td>
                  <td class="num">
                    <span class="score-bar"><i :style="{ width: barWidth(hit.score, topScore) }"></i></span>
                    {{ hit.score }}
                  </td>
                  <td>
                    <span v-if="hit.padded" class="tag">凑数补上，不作答</span>
                    <span v-if="hit.dropped_instructions && hit.dropped_instructions.length" class="tag">
                      含指令式句子，已剔除
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>

            <template v-if="(searchStep.filtered || []).length">
              <p class="hint" style="margin-top: 12px">
                被元数据过滤挡掉的文档（{{ searchStep.filtered.length }} 篇）
              </p>
              <ul class="filtered">
                <li v-for="item in searchStep.filtered" :key="item.doc_id">
                  <b>{{ item.doc_id }}</b>：{{ item.reason }}
                </li>
              </ul>
            </template>
          </section>

          <!-- 证据与引用：回答里的数字和事实分别从哪来 -->
          <section v-if="evidenceStep">
            <h3>证据与引用</h3>
            <template v-for="(item, index) in evidenceStep.data_evidence || []" :key="'e' + index">
              <p class="hint">工具调用</p>
              <p class="mono-block">{{ item.tool }} {{ pretty(item.params) }}</p>
              <pre class="json">{{ pretty(item.result) }}</pre>
            </template>
            <template v-for="(item, index) in evidenceStep.citations || []" :key="'c' + index">
              <p class="hint">引用 {{ item.doc_id }}</p>
              <blockquote>{{ item.quote }}</blockquote>
            </template>
            <p
              v-if="!(evidenceStep.data_evidence || []).length && !(evidenceStep.citations || []).length"
              class="hint"
            >
              这次回答没有用到数据库或文档。
            </p>
          </section>

          <!-- 模型那一侧：只有配了 Key 才非空 -->
          <section v-if="(trace.llm_calls || []).length">
            <h3>模型调用（{{ trace.llm_calls.length }} 次）</h3>
            <div v-for="(call, index) in trace.llm_calls" :key="index" class="llm">
              <p class="hint">
                {{ call.model }} · {{ call.finish_reason }} · {{ call.took_ms }} ms ·
                {{ (call.usage && call.usage.total_tokens) || '?' }} tokens
                <template v-if="call.tool_calls && call.tool_calls.length">
                  · 调了 {{ call.tool_calls.join('、') }}
                </template>
              </p>
              <details>
                <summary>发给模型的提示词</summary>
                <pre class="json">{{ call.prompt }}</pre>
              </details>
              <details v-if="call.raw_reasoning">
                <summary>模型的思考过程（不对外，只在这里看）</summary>
                <pre class="json">{{ call.raw_reasoning }}</pre>
              </details>
              <details v-if="call.raw_content">
                <summary>模型原始输出</summary>
                <pre class="json">{{ call.raw_content }}</pre>
              </details>
            </div>
          </section>
          <p v-else class="hint">
            这次没有调用模型（没有配置 Key，走的是降级回答）。配上 Key 之后，
            这里会列出每一次调用的提示词、结束原因、token 用量与原始输出。
          </p>

          <!-- 错误：真实原因，含堆栈 -->
          <section v-if="(trace.errors || []).length">
            <h3>错误（{{ trace.errors.length }}）</h3>
            <div v-for="(item, index) in trace.errors" :key="index" class="llm">
              <p class="hint">{{ item.where }} · {{ item.type }}：{{ item.message }}</p>
              <pre class="json">{{ item.traceback }}</pre>
            </div>
          </section>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: color-mix(in oklab, var(--text-primary) 32%, transparent);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  z-index: 50;
}

.panel {
  width: min(880px, 100%);
  max-height: 86vh;
  display: flex;
  flex-direction: column;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  box-shadow: 0 24px 60px -24px rgba(0, 0, 0, 0.5);
  overflow: hidden;
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.panel-head h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 620;
}

.panel-body {
  padding: 4px 20px 20px;
  overflow-y: auto;
}

section {
  margin-top: 18px;
}

section h3 {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 620;
  letter-spacing: 0.3px;
  color: var(--text-secondary);
}

code {
  font-size: 12px;
}

.mono-block {
  margin: 0 0 6px;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--text-primary);
  background: var(--surface-2);
  border-radius: 8px;
  padding: 8px 10px;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 时间线：条长表示耗时占比 */
.timeline {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 6px;
}

.timeline li {
  display: grid;
  grid-template-columns: 132px minmax(0, 1fr) 72px;
  align-items: center;
  gap: 10px;
  font-size: 12.5px;
}

.step-name {
  color: var(--text-secondary);
}

.step-bar {
  height: 8px;
  border-radius: 999px;
  background: var(--surface-2);
  overflow: hidden;
}

.step-bar > i {
  display: block;
  height: 100%;
  border-radius: 0 4px 4px 0;
  background: var(--series-1);
}

.step-time {
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
}

.facts {
  margin: 0;
  display: grid;
  /* 列宽要放得下「2026-06-18 至 2026-06-18」这种最长的值，
     否则下面那条 nowrap 会把行撑破（实测过：252px 时内容宽 285） */
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 4px 16px;
  font-size: 12.5px;
}

.facts > div {
  display: flex;
  gap: 8px;
  min-width: 0;
}

.facts dt {
  color: var(--text-muted);
  min-width: 88px;
  flex: none;
}

.facts dd {
  margin: 0;
  color: var(--text-primary);
  /* 日期区间这类值不该被折行从中间断开 */
  white-space: nowrap;
}

table.mini {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}

table.mini th,
table.mini td {
  text-align: left;
  padding: 5px 8px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}

table.mini th {
  font-size: 11px;
  color: var(--text-muted);
  border-bottom-color: var(--axis);
}

.score-bar {
  display: inline-block;
  width: 46px;
  height: 6px;
  border-radius: 999px;
  background: var(--seq-track);
  overflow: hidden;
  vertical-align: middle;
  margin-right: 6px;
}

.score-bar > i {
  display: block;
  height: 100%;
  background: var(--seq-strong);
}

.tag {
  display: inline-block;
  font-size: 11px;
  color: var(--text-secondary);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 1px 8px;
  margin-right: 4px;
}

.filtered {
  margin: 0;
  padding-left: 18px;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text-secondary);
}

.filtered b {
  color: var(--text-primary);
  font-weight: 600;
}

blockquote {
  margin: 0 0 6px;
  padding-left: 10px;
  border-left: 2px solid var(--seq-track);
  font-size: 12.5px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.json {
  margin: 0 0 10px;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--text-secondary);
  background: var(--surface-2);
  border-radius: 8px;
  padding: 8px 10px;
  max-height: 260px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.llm {
  margin-bottom: 12px;
}

details > summary {
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
  list-style: none;
  padding: 3px 0;
}

details > summary::-webkit-details-marker {
  display: none;
}

details > summary::before {
  content: '▸ ';
  color: var(--text-muted);
}

details[open] > summary::before {
  content: '▾ ';
}
</style>
