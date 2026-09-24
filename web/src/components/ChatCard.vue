<script setup>
/**
 * 运营问答对话框。后端是契约 §5 的 `POST /api/chat`。
 *
 * 三个约束决定了这里的写法：
 *
 * 1. **同一个 `session_id` 才是一段对话**（契约 §5 要求支持追问、且不同 session 不能串线）。
 *    所以 `session_id` 由前端持有，「新对话」时换一个。
 * 2. **接口永远返回 200**，失败会体现为 `answer_type: "refusal"` 而不是异常。
 *    所以这里的错误处理只管网络层的意外，业务失败当普通回答渲染。
 * 3. **文档正文与问题都是不可信数据**：全部用 `{{ }}` 插值（Vue 会转义），
 *    不用 `v-html`——知识库里就埋着「忽略之前的指令」这类句子。
 */
import { nextTick, ref } from 'vue'

import { api } from '@/api'
import TracePanel from '@/components/TracePanel.vue'

const messages = ref([])
const draft = ref('')
const pending = ref(false)
const error = ref('')
const scroller = ref(null)
/** 非空时打开调试面板，值是这次回答的 trace_id。 */
const openedTrace = ref('')
let sessionId = newSessionId()

/** 没带 session_id 就没有「同一段对话」可言，所以每次开会话都生成一个。 */
function newSessionId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return `s-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

/** 契约 §5 的五种 answer_type，用中文写清楚它是什么意思。 */
const ANSWER_LABELS = {
  data: '查了数据库',
  doc: '查了知识库',
  hybrid: '数据库 + 知识库',
  refusal: '拒答',
  clarify: '需要补充',
}

const EXAMPLES = [
  '618 当天 S02 的牛肉poke 卖了多少份，达到目标了吗？',
  '外卖订单多久内可以申请退款？',
  '7 月整体的净营业额是多少？',
  'S04 为什么不卖吞拿鱼三明治了？',
]

async function scrollToLatest() {
  await nextTick()
  const box = scroller.value
  if (box) box.scrollTop = box.scrollHeight
}

async function ask(question) {
  const text = (question ?? draft.value).trim()
  if (!text || pending.value) return
  draft.value = ''
  error.value = ''
  messages.value.push({ role: 'user', text })
  pending.value = true
  await scrollToLatest()
  try {
    const answer = await api.chat(sessionId, text)
    messages.value.push({
      role: 'assistant',
      text: answer.answer,
      answerType: answer.answer_type,
      citations: answer.citations || [],
      evidence: answer.data_evidence || [],
      traceId: answer.trace_id,
    })
  } catch (problem) {
    // 契约保证业务失败也是 200，走到这里基本只有网络层的问题。
    error.value = `没能拿到回答：${problem.message}`
  } finally {
    pending.value = false
    await scrollToLatest()
  }
}

function startOver() {
  messages.value = []
  error.value = ''
  sessionId = newSessionId()
}

function onKeydown(event) {
  // Enter 发送，Shift+Enter 换行——运营最常用的两种输入习惯。
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    ask()
  }
}

function evidenceSummary(item) {
  const params = item.params || {}
  const parts = Object.entries(params)
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .map(([key, value]) => `${key}=${value}`)
  return `${item.tool || item.sql || '查询'}(${parts.join(', ')})`
}

function pretty(value) {
  try {
    return JSON.stringify(value, null, 1)
  } catch (problem) {
    return String(value)
  }
}
</script>

<template>
  <section class="card chat-card">
    <header>
      <div>
        <h2>问 AI</h2>
        <p class="hint">
          用大白话问经营数字或公司规定 · 支持追问（同一段对话里继续说「那 7 月呢」）
        </p>
      </div>
      <button v-if="messages.length" class="ghost" type="button" @click="startOver">新对话</button>
    </header>

    <!-- 空状态给几个能直接点的例子，比让人对着空框发呆有用 -->
    <div v-if="!messages.length" class="examples">
      <span class="hint">试试：</span>
      <button v-for="example in EXAMPLES" :key="example" class="chip" type="button" @click="ask(example)">
        {{ example }}
      </button>
    </div>

    <div v-else ref="scroller" class="thread" aria-live="polite">
      <div v-for="(message, index) in messages" :key="index" class="turn">
        <template v-if="message.role === 'user'">
          <p class="bubble-me">{{ message.text }}</p>
        </template>

        <template v-else>
          <div class="bubble-ai">
            <p class="answer">{{ message.text }}</p>

            <p class="meta">
              <span class="badge" :data-type="message.answerType">
                {{ ANSWER_LABELS[message.answerType] || message.answerType }}
              </span>
              <!-- 答得不对时，从这里进去看它到底怎么想的 -->
              <button class="trace-link" type="button" @click="openedTrace = message.traceId">
                处理过程 {{ message.traceId }}
              </button>
            </p>

            <details v-if="message.citations.length || message.evidence.length" class="grounds">
              <summary>
                依据（{{ message.citations.length }} 条引用 · {{ message.evidence.length }} 次查询）
              </summary>

              <div v-for="citation in message.citations" :key="citation.doc_id + citation.quote" class="ground">
                <p class="ground-head">{{ citation.doc_id }}</p>
                <blockquote>{{ citation.quote }}</blockquote>
              </div>

              <div v-for="(item, position) in message.evidence" :key="position" class="ground">
                <p class="ground-head">{{ evidenceSummary(item) }}</p>
                <pre class="ground-body">{{ pretty(item.result) }}</pre>
              </div>
            </details>
          </div>
        </template>
      </div>

      <p v-if="pending" class="bubble-ai pending">正在查…</p>
    </div>

    <p v-if="error" class="notice error" style="margin-top: 12px" role="alert">{{ error }}</p>

    <div class="composer">
      <label class="sr-only" for="chat-input">提问</label>
      <textarea
        id="chat-input"
        v-model="draft"
        rows="2"
        placeholder="例如：S03 六月第二周营业额为什么这么低？"
        :disabled="pending"
        @keydown="onKeydown"
      ></textarea>
      <button class="primary" type="button" :disabled="pending || !draft.trim()" @click="ask()">
        {{ pending ? '查询中' : '提问' }}
      </button>
    </div>

    <TracePanel v-if="openedTrace" :trace-id="openedTrace" @close="openedTrace = ''" />
  </section>
</template>

<style scoped>
.chat-card {
  margin-top: 16px;
}

.examples {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.chip {
  font: inherit;
  font-size: 12.5px;
  color: var(--text-secondary);
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 5px 12px;
  cursor: pointer;
  transition: background 140ms ease, color 140ms ease, border-color 140ms ease;
}

.chip:hover {
  background: color-mix(in oklab, var(--series-1) 10%, transparent);
  border-color: color-mix(in oklab, var(--series-1) 40%, var(--border));
  color: var(--text-primary);
}

.thread {
  display: grid;
  gap: 12px;
  max-height: 420px;
  overflow-y: auto;
  padding-right: 4px;
  margin-bottom: 12px;
}

.turn {
  display: grid;
  gap: 8px;
}

.bubble-me {
  margin: 0;
  justify-self: end;
  max-width: 82%;
  padding: 9px 13px;
  border-radius: 14px 14px 4px 14px;
  background: var(--series-1);
  color: #fff;
  font-size: 13.5px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.bubble-ai {
  max-width: 100%;
  padding: 12px 14px;
  border-radius: 14px 14px 14px 4px;
  background: var(--surface-2);
  border: 1px solid var(--border);
}

.bubble-ai.pending {
  color: var(--text-muted);
  font-size: 13px;
  justify-self: start;
}

.answer {
  margin: 0;
  font-size: 13.5px;
  line-height: 1.7;
  /* 回答里会有换行与文档原文，按原样保留 */
  white-space: pre-wrap;
  word-break: break-word;
}

.meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin: 10px 0 0;
}

.badge {
  font-size: 11.5px;
  padding: 2px 9px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface-1);
  color: var(--text-secondary);
}

/* 小圆点带颜色，文字仍然承担含义——颜色不是唯一的编码 */
.badge::before {
  content: '';
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 999px;
  margin-right: 6px;
  vertical-align: middle;
  background: var(--text-muted);
}

.badge[data-type='data']::before {
  background: var(--series-1);
}

.badge[data-type='doc']::before {
  background: var(--series-2);
}

.badge[data-type='hybrid']::before {
  background: linear-gradient(90deg, var(--series-1) 50%, var(--series-2) 50%);
}

.badge[data-type='refusal']::before,
.badge[data-type='clarify']::before {
  background: var(--text-muted);
}

.trace-link {
  font: inherit;
  font-size: 11.5px;
  color: var(--text-secondary);
  background: transparent;
  border: 0;
  border-bottom: 1px dashed var(--axis);
  padding: 0 0 1px;
  cursor: pointer;
  font-variant-numeric: tabular-nums;
}

.trace-link:hover {
  color: var(--text-primary);
  border-bottom-color: var(--series-1);
}

.grounds {
  margin-top: 10px;
  border-top: 1px solid var(--border);
  padding-top: 8px;
}

.grounds > summary {
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
  list-style: none;
}

.grounds > summary::-webkit-details-marker {
  display: none;
}

.grounds > summary::before {
  content: '▸ ';
  color: var(--text-muted);
}

.grounds[open] > summary::before {
  content: '▾ ';
}

.ground {
  margin-top: 10px;
  padding-left: 10px;
  border-left: 2px solid var(--seq-track);
}

.ground-head {
  margin: 0 0 4px;
  font-size: 11.5px;
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
}

blockquote {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--text-primary);
  white-space: pre-wrap;
}

.ground-body {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--text-secondary);
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  overflow-x: auto;
}

.composer {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}

.composer textarea {
  flex: 1 1 auto;
  font: inherit;
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--text-primary);
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius-control);
  padding: 9px 11px;
  resize: vertical;
  min-height: 44px;
}

.composer textarea:focus-visible {
  outline: 2px solid var(--series-1);
  outline-offset: 1px;
}

.composer textarea:disabled {
  opacity: 0.6;
}

.primary {
  font: inherit;
  font-size: 13.5px;
  font-weight: 600;
  color: #fff;
  background: var(--series-1);
  border: 1px solid transparent;
  border-radius: var(--radius-control);
  padding: 11px 20px;
  cursor: pointer;
  transition: filter 140ms ease;
}

.primary:hover:not(:disabled) {
  filter: brightness(1.08);
}

.primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
