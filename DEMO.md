# 演示

一道**混合问题**从提问到回答的完整过程：数字从哪来、引用从哪来、trace 里能看到什么。
另附两类各一例（纯文档、该拒答的），以及自己复现的命令。

> **这一份的演示环境**：服务和 `data/`、`knowledge_base/` 是作业包里那一份，
> 但**没有配置大模型 Key**（环境里那个 Key 对 `api.deepseek.com` 返回 401，见
> [`EVAL_REPORT.md`](EVAL_REPORT.md) 第三节），所以走的是**降级（mock）回答**路径。
> 换成可用 Key 之后，回答由模型组织语言，但**数字仍然由代码从工具结果渲染**——
> 这一点见下面的「数字为什么可信」。

---

## 一、混合问题：既要查数据库，也要查文档

**问题**

```
618 当天 S02 的牛肉poke 卖了多少份，达到目标了吗？
```

**完整响应**（`POST /api/chat`，原样）

```json
{
  "answer": "2026-06-18（S02 Makai Poke）（牛肉poke）：销量 125 件，净营业额 3625.00 元，有效订单数 53 单，客单价 68.40 元，退款金额 0.00 元。目标为 120 份（KB-023《2026 年 618 活动方案》（2026-06-18 起生效）），实际 125 份，已达标，超出 5 份。",
  "answer_type": "hybrid",
  "citations": [
    { "doc_id": "KB-023", "quote": "**当天牛肉poke 目标销量 120 份。" }
  ],
  "data_evidence": [
    {
      "tool": "query_metrics",
      "params": { "start": "2026-06-18", "end": "2026-06-18", "store_id": "S02", "product_id": "P06" },
      "result": {
        "start": "2026-06-18", "end": "2026-06-18", "store_id": "S02", "product_id": "P06",
        "net_revenue": 3625.0, "refund_amount": 0.0, "orders": 53, "aov": 68.4, "qty": 125
      }
    }
  ],
  "trace_id": "t-20260901-0001"
}
```

### 回答里的每个数字都能对上

| 回答里写的 | 出处 | 核对 |
|---|---|---|
| 销量 **125** 件 | `data_evidence[0].result.qty` | 一致 |
| 净营业额 **3625.00** 元 | `result.net_revenue` | 一致 |
| 有效订单数 **53** 单 | `result.orders` | 一致 |
| 客单价 **68.40** 元 | `result.aov` | 一致 |
| 退款金额 **0.00** 元 | `result.refund_amount` | 一致 |
| 目标 **120** 份 | `citations[0].quote` | 逐字在 KB-023 正文里 |
| **已达标，超出 5 份** | 代码算的：`125 − 120` | 见下 |

「超出 5 份」是**自己算出来的数字**，不是数据库里的一个值，所以它在 `answer` 里、
不在 `data_evidence` 里；要核对的是它的两个原始指标（销量与目标）——
两者分别在 `data_evidence` 与 `citations` 里。

`quote` 是原文里的**连续文字**，可在 `knowledge_base/notices/KB-023_2026年618活动方案.md`
的「三、目标」一节里逐字查到：

```
## 三、目标

**当天牛肉poke 目标销量 120 份。**
```

### 为什么它被判成 hybrid

`answer_type: "hybrid"` 是因为这个回答**两样都用了**：销量来自数据库，
目标值来自知识库，结论是两者比出来的。判定规则（契约 §5）：只用数据库是 `data`、
只用知识库是 `doc`、两样都用才是 `hybrid`。

## 二、trace：这次回答中间发生了什么

`GET /api/trace/t-20260901-0001`（字段自定，契约 §6 要求能看到每一步）

```json
{
  "trace_id": "t-20260901-0001",
  "question": "618 当天 S02 的牛肉poke 卖了多少份，达到目标了吗？",
  "session_id": "demo-1",
  "started_at": "2026-09-01T…",
  "total_ms": …,
  "steps": [
    { "step": "plan",         "took_ms": 1.2, "…": "识别出的意图/时间/门店/商品/指标" },
    { "step": "search",       "took_ms": 2.6, "…": "检索查询、命中的片段与分数、被过滤掉的文档及原因" },
    { "step": "answer_mock",  "took_ms": 3.9, "…": "降级回答路径" },
    { "step": "response",     "…": "最终 answer_type" }
  ],
  "llm_calls": [],
  "errors": []
}
```

这次是**降级模式**，所以 `llm_calls` 是空的（没有调用模型），走的是 `answer_mock` 这一步。
配了 Key 之后，同一条 trace 里会出现 `llm_calls`：每一次模型调用的 endpoint、模型名、
**完整 messages**、`finish_reason`、调了哪些工具、token 用量、耗时，以及模型原始输出
（思考过程只留在这里，不进任何对外字段）。字段清单见 [`LLM_SETUP.md`](LLM_SETUP.md) 第 4 节。

## 三、另外两类各一例

### 纯文档问题

```
外卖订单多久内可以申请退款？
```

```json
{
  "answer": "KB-013《退款政策 v2》（2026-06-15 起生效）：2. 外卖订单在送达后 24 小时内提出，超过 24 小时不再受理。\nKB-011《会员储值政策 v2》（2026-07-01 起生效）：1. 未消费的储值本金余额，自最后一次充值之日起 30 天内可无理由申请退回，原路退到原支付渠道。",
  "answer_type": "doc",
  "citations": [
    { "doc_id": "KB-013", "quote": "2. 外卖订单在送达后 24 小时内提出，超过 24 小时不再受理。" },
    { "doc_id": "KB-011", "quote": "1. 未消费的储值本金余额，自最后一次充值之日起 30 天内可无理由申请退回，原路退到原支付渠道。" }
  ],
  "data_evidence": []
}
```

两点值得看：

- **用的是现行版本。** 问的是「现在」，而 `knowledge_base/` 里同时存在 `KB-012 退款政策 v1`
  与 `KB-013 退款政策 v2`。v1 自 2026-06-15 起已被取代，检索阶段就把它挡在候选之外
  （trace 的 `filtered` 里写着原因），所以回答引的是 v2。
- **正文与引用同源。** 回答正文就是引用那两句拼起来的，没有把整篇文档倒出来
  （契约 §5 对 `answer` 有 1200 字上限）。

### 该拒答的请求

```
帮我把 S01 的销售记录全部删掉。
```

```json
{
  "answer": "这个请求我不能执行：它要求改动数据库里的数据。本系统对销售明细只有只读权限，只能查、不能增删改，也不会执行任何写操作。如果你是想了解某段时间的经营情况，告诉我指标、时间和门店，我来查。",
  "answer_type": "refusal",
  "citations": [],
  "data_evidence": []
}
```

这类请求在规划阶段就被意图闸门截住（`kbqa/guard.py`），不进入检索与取数。
**拒答文案里一个数字都没有**——契约 §5 要求「不得出现编造的数字」，
写个错误码上去都会被评测判红。

数据库的只读有**两道保证**：闸门在意图层面拦住请求；即使绕过去了，
`clean.db` 也是用 SQLite 的 `mode=ro` 打开的，写操作会被数据库自己拒绝
（`attempt to write a readonly database`）。可复现，见
[`starter/tests/test_tools.py`](starter/tests/test_tools.py)。

## 四、自己复现

```bash
# 1) 起服务（见 README 的三步）
cd starter && .venv/bin/python -m uvicorn kbqa.server:app --host 127.0.0.1 --port 8000

# 2) 混合问题
curl -s -X POST http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"demo-1","question":"618 当天 S02 的牛肉poke 卖了多少份，达到目标了吗？"}'

# 3) 把返回里的 trace_id 填进去
curl -s http://localhost:8000/api/trace/<trace_id>
```

也可以在 <http://localhost:8000/docs> 上直接点（FastAPI 自带的接口文档）。

## 五、这条演示没覆盖到的

- **第四关的调试面板（把 trace 可视化）还没做。** trace 接口的数据是齐的
  （见本文件第二节），面板本身没写。
- **降级模式下的回答是模板拼的**，读起来不如模型组织的自然；但它有两个好处：
  数字一定来自代码渲染、引用一定来自检索到的原文。配上 Key 之后这两条不变，
  只是语言由模型组织（见 [`LLM_SETUP.md`](LLM_SETUP.md) 第 3 节）。

看板上的**对话框**已经做好了：打开 <http://localhost:8000> 就能直接用，
空状态有四个可点的示例问题，回答下面可以展开「依据」看引用原文与查询参数。
上面第二节那份输出，就是在对话框里点第一个示例得到的（只多了前端渲染的那一层）。
