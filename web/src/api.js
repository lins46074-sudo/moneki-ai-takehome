/** 后端接口封装。开发时走 Vite 代理，生产由 FastAPI 同源托管，都用相对路径。 */

/** 把空值过滤掉，后端只收到真正有意义的查询参数。 */
function query(params) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params || {})) {
    if (value === undefined || value === null || value === '') continue
    search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

async function request(path, { params, method = 'GET', body } = {}) {
  const response = await fetch(`/api${path}${query(params)}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!response.ok) {
    // 后端按契约返回 JSON 错误（如日期格式不对时的 400），把原因带出去给用户看。
    let detail = `请求失败（HTTP ${response.status}）`
    try {
      const payload = await response.json()
      if (payload && (payload.error || payload.detail)) detail = payload.error || payload.detail
    } catch (error) {
      /* 响应体不是 JSON，就用默认文案 */
    }
    throw new Error(detail)
  }
  return response.json()
}

export const api = {
  meta: () => request('/meta'),
  health: () => request('/health'),
  summary: (params) => request('/metrics/summary', { params }),
  daily: (params) => request('/metrics/daily', { params }),
  topProducts: (params) => request('/metrics/top_products', { params }),
  byStore: (params) => request('/metrics/by_store', { params }),
  dataQuality: () => request('/data_quality'),

  /**
   * 问答。同一个 session_id 的多次请求算同一段对话，所以由调用方持有它。
   * 契约 §5：无论内部出什么错，这个接口都返回 200 与合法 JSON——
   * 也就是说失败会体现为 answer_type 里的 refusal，而不是走到这里抛异常。
   */
  chat: (sessionId, question) =>
    request('/chat', { method: 'POST', body: { session_id: sessionId, question } }),
  trace: (traceId) => request(`/trace/${encodeURIComponent(traceId)}`),
}

/** 看板上的所有数字都由同一个筛选条件决定，这里统一拼参数。 */
export function sliceParams(filters) {
  return {
    start: filters.start,
    end: filters.end,
    store_id: filters.storeId || undefined,
    product_id: filters.productId || undefined,
  }
}
