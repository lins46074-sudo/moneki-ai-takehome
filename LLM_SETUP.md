# LLM 接入说明

按 `docs/API_CONTRACT.md` 第 7.4 节的骨架写。目标是：**你们照着这份说明，不改代码就能把服务切到
DeepSeek `deepseek-flash`、换成你们自己的 Key。**

## 1. 用了什么

| 项 | 值 |
|---|---|
| 厂商 | DeepSeek（官方 API） |
| 模型名 | `deepseek-flash`（只从环境变量读，代码里没有任何模型名） |
| 协议 | OpenAI 兼容的 **Chat Completions**（契约 §7.1 推荐路线） |
| SDK | **没有用 SDK**。直接用 `httpx` 发一次 `POST {LLM_BASE_URL}/chat/completions` |
| 依赖版本 | `httpx`（`starter/requirements.txt`）；`fastapi` / `uvicorn` 是服务本身的依赖 |
| 思考模式 | **保持开启**（不传 `thinking`），理由见第 8 节 |
| 工具调用 | OpenAI 函数调用格式，`tools` + `tool_choice: "auto"`，最多 4 轮（`live.py` 的 `MAX_TOOL_ROUNDS`） |

请求体只有这几个字段（`starter/kbqa/llm.py::_body`）：

```json
{
  "model": "<LLM_MODEL>",
  "messages": [...],
  "max_tokens": 4096,
  "tools": [...],
  "tool_choice": "auto"
}
```

`tools` 是**每次都带**的（共 10 个：`query_metrics`、`daily_metrics`、`payment_mix`、`top_products`、
`by_store`、`by_store_category`、`compare_periods`、`unit_price_check`、`run_sql`、`search_kb`，
定义在 `starter/kbqa/toolspec.py`）。**没有** `temperature`、`seed`、`n`、`parallel_tool_calls`、
`response_format`、`stream` 这些参数——文档里没有的、以及思考模式下不生效的，一律不发。
认证头是 `Authorization: Bearer <LLM_API_KEY>`，另一个头是 `Content-Type: application/json`。

## 2. 配置从哪里读

**全部只从环境变量读，没有任何配置文件、也没有命令行参数。** 读取位置是 `starter/kbqa/config.py::load_settings()`。

| 变量 | 默认值 | 含义 |
|---|---|---|
| `LLM_BASE_URL` | 空 | 模型服务地址。**原样使用**：不补 `/v1`、不截路径、不取域名（只 `rstrip("/")` 掉末尾斜杠）。请求打到 `{LLM_BASE_URL}/chat/completions` |
| `LLM_API_KEY` | 空 | Key。为空即判定为没有模型 |
| `LLM_MODEL` | 空 | 模型名，原样放进请求体的 `model` 字段 |
| `LLM_TIMEOUT` | `120` | **单次**模型调用的超时（秒），契约 §7.3 要求不小于 120 |
| `CHAT_BUDGET` | `150` | `/api/chat` 的整体预算（秒），留出余量以满足契约的 180 秒上限 |

另有三个与模型无关的路径变量：`DATA_DIR`、`KB_DIR`、`VAR_DIR`（见 README 的重建命令）。

**这三个值有一项为空就进入 mock 降级模式**（`config.py::Settings.live`：三个变量都非空才算 live）。
启动时**不做任何校验**：不检查 Key 格式、不查余额、不列模型、不建额外连接——契约 §7.2 明确不要做这些。
`/api/health` 会如实报告当前是 `live` 还是 `mock`。

## 3. 怎么换成你们的

三个值，**不需要改任何代码**：

```bash
export LLM_BASE_URL=https://api.deepseek.com
export LLM_MODEL=deepseek-flash
export LLM_API_KEY=<你们的 Key>

# 也可以用契约 §7.5 的代理，把地址指向它，这样你们能看到每一条进出流量：
# export LLM_BASE_URL=http://127.0.0.1:<代理端口>
```

然后重启服务：

```bash
cd starter
.venv/bin/python -m uvicorn kbqa.server:app --host 127.0.0.1 --port 8000
# Windows: .venv\Scripts\python -m uvicorn kbqa.server:app --host 127.0.0.1 --port 8000
```

**改完要重启，不要重新执行 `make rebuild`。** 重建只负责清洗表与检索索引，与模型配置无关
（`var/clean.db` 与 `.cache/index.json` 里不含任何模型信息，换 Key 也不需要重建）。
启动后用 `GET /api/health` 确认 `llm_mode` 变成 `"live"` 即可。

如果 `LLM_BASE_URL` 带路径前缀（比如代理的 `http://127.0.0.1:53120/ds-gw`），直接照抄整条地址，
服务会原样拼上 `/chat/completions`——不要自己补 `/v1`，也不要只填域名。

## 4. 怎么看到发给模型的请求

两条路，**都可用，不冲突**。

### 4.1 代理（完整的请求与响应）

契约 §7.5 提供的方式，把服务指向代理即可：

```bash
python3 eval/llm_gateway.py proxy --upstream https://api.deepseek.com --log llm_traffic.jsonl
# 用它打印的地址作为 LLM_BASE_URL 启动服务
```

`llm_traffic.jsonl` 里是每一次请求与响应的原文，**包括工具定义和每一轮的消息**。

### 4.2 trace（不用起代理也能看）

每次 `/api/chat` 都会把**每一次模型调用**记进 trace（契约 §6 的调试面板就是把它可视化）：

```bash
curl -s "http://localhost:8000/api/trace/<trace_id>" | python3 -m json.tool
```

`trace["llm"]` 是一个数组，每次调用一条，字段如下：

| 字段 | 内容 |
|---|---|
| `endpoint` / `model` | 实际打到的地址与模型名 |
| `prompt` | **发给模型的完整 messages**（JSON 原文，超过 4000 字才截断） |
| `messages` / `tools` | 消息条数与工具个数 |
| `status` / `finish_reason` | HTTP 状态码与结束原因 |
| `content_chars` / `tool_calls` | 正文长度、这一轮调了哪些工具 |
| `has_reasoning` / `raw_reasoning` | 有没有思考内容、思考原文（**只留在 trace 里，不进任何对外字段**） |
| `raw_content` | 模型原始输出 |
| `usage` | token 用量 |
| `took_ms` | 这一次调用耗时 |
| `error` / `detail` | 出错时的原因 |

一段脱敏样例（`prompt` 字段截取开头，`reasoning_content` 只留标记）：

```json
[
  {
    "endpoint": "http://127.0.0.1:53120/ds-gw/chat/completions",
    "model": "deepseek-flash",
    "messages": 2,
    "tools": 10,
    "prompt": "[{\"role\": \"system\", \"content\": \"你是一家连锁餐饮公司的经营分析助手……今天是 2026-09-01……\"}, {\"role\": \"user\", \"content\": \"618 当天 S02 的牛肉poke 卖了多少份，达到目标了吗？\"}]",
    "status": 200,
    "finish_reason": "tool_calls",
    "content_chars": 0,
    "tool_calls": ["query_metrics"],
    "has_reasoning": true,
    "raw_reasoning": "（思考过程，只在 trace 里留痕，不对外）",
    "took_ms": 4210.4,
    "usage": {"prompt_tokens": 1180, "completion_tokens": 214, "total_tokens": 1394}
  }
]
```

**两点要说清楚**：

- trace 里的 `prompt` 记的是 messages，**工具定义没有整份记进去**（只记了个数）。要看工具 schema 的原文，
  走 4.1 的代理；或者直接看源码 `starter/kbqa/toolspec.py`——工具定义是静态的，不随请求变化。
- trace 只在内存里保留最近若干条，进程重启即清空（`starter/kbqa/trace.py`）。要留存就及时取。

## 5. 没有 Key 时会怎样

**服务照常启动，四个接口全部可用**（契约 §7.2 第 3 条）：

| 接口 | 没有 Key 时的行为 |
|---|---|
| `GET /api/health` | 200，`llm_mode: "mock"`，其余字段照常 |
| `GET /api/metrics/*` | 200，**与有没有 Key 完全无关**（取数路径不经过模型） |
| `POST /api/retrieve` | 200，检索不经过模型 |
| `POST /api/chat` | 200，走**降级回答**：本地模板作答，不调用任何模型 |

降级策略：`service._run_engine()` 里判断 `settings.live`，为假就走 `Answerer` 的模板路径——
数字仍然由代码从数据库渲染，文档事实仍然来自检索到的原文并附 `citations`，
`trace_id` 照常返回。会在 trace 的 `plan` / `answer_mock` 两个步骤里标注走的是降级路径。

模型不可用（超时、错误码、空回答、异常 `finish_reason`）时**同样**不会返回 500，
而是返回 HTTP 200 加结构化 `refusal`，真实原因写进 trace 与 `notes`——
这一点由预检的 P8/P9/P11 三个场景（32 次请求）验证过。

## 6. 依赖与安装

没有额外依赖，**不需要下载任何模型文件**：`httpx` 已经在 `starter/requirements.txt` 里，
是服务本身的依赖之一。首次启动耗时以秒计（索引与清洗表的生成见 README 的重建命令）。
不引入向量模型，因此没有模型体积、也没有 GPU/CPU 算力要求。

## 7. 自测结果

走的就是契约 §7.1 的 OpenAI 兼容路线，所以按 §7.5 跑了接入预检（**不花钱、不需要 Key**）：

```bash
python eval/llm_gateway.py preflight --service-url http://localhost:8000 --out eval/preflight
```

预检在本机起了一个按 DeepSeek 文档行为模拟的假模型，驱动 `/api/chat` 跑完 16 个场景、
32 次问答。**总体结论：没有失败项，14 项检查里 14 项通过。**

| 编号 | 检查项 | 结果 | 说明 |
|---|---|---|---|
| P1 | 请求发到了注入的 `LLM_BASE_URL`（含路径前缀） | 通过 | 共观察到 60 次 `POST /ds-gw/chat/completions` |
| P2 | 请求里的 `model` 等于注入的 `LLM_MODEL` | 通过 | 全部请求都用了 `preflight-model-7f3a` |
| P3 | 注入的 Key 以 `Authorization: Bearer` 发送 | 通过 | 全部请求都带了正确的 Bearer Key |
| P4 | 只用了 DeepSeek 文档列出的顶层参数 | 通过 | 只出现了文档列出的顶层参数 |
| P5 | `max_tokens` 不设，或不小于 2048 | 通过 | `max_tokens` 都不小于 2048 |
| P6 | 没有访问 `{prefix}/chat/completions` 之外的任何路径 | 通过 | 只访问了 `POST /ds-gw/chat/completions` |
| P7 | 工具定义规范，每个工具调用以 `role=tool` + `tool_call_id` 回传 | 通过 | 44 个工具调用的结果都正确回传 |
| P8 | 每个场景都返回 HTTP 200 与字段完整的合法 JSON | 通过 | 32 次问答全部 200 |
| P9 | 模型不可用时给出结构化 `refusal`，`answer` 从不是空串 | 通过 | 失败场景都是一次性的标记，没有漏进对外字段 |
| P10 | 思考内容没有漏进 `answer` / `citations` / `data_evidence` | 通过 | 32 次回答里思考标记都没出现在任何对外字段 |
| P11 | `/api/chat` 在时限内返回（含长时间无响应） | 通过 | 最慢一次 120.10 秒，在 180 秒以内 |
| P12 | 注入环境变量后 `/api/health` 报告 `llm_mode: "live"` | 通过 | `llm_mode = live` |
| P13 | 多轮工具调用之间 `reasoning_content` 原样回传 | 通过 | 18 次多轮请求都原样回传 |
| P14 | 保持连接的空行与 SSE 注释没有把服务弄坏 | 通过 | 正文前的空行与 `: keep-alive` 注释都被跳过 |

完整报告（含逐项证据）：[`eval/preflight/preflight_report.md`](eval/preflight/preflight_report.md)。

### 关于这次预检的两点说明

- 预检用的是假模型，所以它验证的是**接入方式**，不是回答质量。回答质量看
  [`EVAL_REPORT.md`](EVAL_REPORT.md)。
- 预检不需要 Key，也不联网；上面那张表就是交付时的原始输出。

### 我们自己没测到的

预检过了不等于「真实模型下也一切正常」。**我们手上没有可用的 DeepSeek Key**
（环境里那个对 `api.deepseek.com` 返回 401，见 EVAL_REPORT 第三节），所以**真实模型下的端到端跑分还没做**。
切到你们的 Key 之后建议先跑一遍公开题库确认：

```bash
python eval/run_eval.py --base-url http://localhost:8000 --questions eval/public_questions.jsonl
```

## 8. 已知限制

1. **思考模式保持开启，没有关。** 理由是这类问题需要规划（先决定查数据还是查文档、查哪段时间、
   用哪个工具），思考开着明显更稳；代价是每次问答慢一些、贵一些。关掉的话
   `reasoning_content` 相关的两项预检会显示「未检查」而不是「通过」（预检文档里说明这不扣分）。
   想关掉只需在 `llm.py::_body()` 里加一个 `"thinking": {"type": "disabled"}`——这是唯一需要改代码的地方，
   目前**没有**这么做，因为默认路线要按契约 §7.1 走。
2. **不用流式输出。** `stream` 一律不发，前端因此没有「思考中」的逐字状态。契约 §7.3 关于流式的
   那条规则（先到的是 `delta.reasoning_content`）在非流式下不适用。
3. **trace 里的工具定义只记了个数**，没记 schema 原文（见第 4 节）。要看完整请求走代理。
4. **trace 只在内存里**，进程重启就没了；也没有做落盘与轮转。
5. **没有做并发限流。** 契约 §7.3 提到 429 是并发超限，我们的处理是「按可重试错误重试一次」，
   没有做排队或降并发。
6. **真实模型下的端到端表现未验证**——原因见第 7 节的最后一段。

## 9. 换了知识库或数据之后要做什么

模型配置与它们无关（第 3 节），但**索引要重建**：

```bash
cd starter && make rebuild          # 或 .venv/bin/python -m kbqa.rebuild
```

重建与模型无关：这一步不调用模型，也不需要 Key。
