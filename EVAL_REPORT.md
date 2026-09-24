# 评测报告

公开题库（`eval/public_questions.jsonl`，55 题 / 61 turn / 满分 100）的历次得分。
每次得分都记下运行命令、代码的 commit、模型与关键配置（**不含任何 Key**）、以及当时是否配了 Key。

## 一、结果一览

| # | 日期 | 代码（commit） | 大模型 | 得分 | 原始报告 |
|---|---|---|---|---|---|
| A | 2026-09-24 | 原始 starter `56f7a1f` | 无（mock 降级） | **17.00 / 100（17.0%）** | [`eval/runs/starter-baseline-mock/`](eval/runs/starter-baseline-mock/) |
| B | 2026-09-24 | 原始 starter `56f7a1f` | **Key 无效**（见第三节） | 13.00 / 100（13.0%）**不计入基线** | [`eval/runs/starter-baseline-live/`](eval/runs/starter-baseline-live/) |
| C | 2026-09-24 | 第一关结束时 `3977bd7` | 无（mock 降级） | **44.50 / 100（44.5%）** | [`eval/runs/gate1-current/`](eval/runs/gate1-current/) |

**前两轮与第三轮是同一种模式（无 Key）下的可比数据**：

- 原始 starter：**17.00**
- 第一关结束后：**44.50**
- 第一关的工作把分数提高了 **+27.50**（27 题全绿 → 27 题全绿里换了 18 题）

真实模型（DeepSeek `deepseek-flash`）的基线**还没测到**，原因见第三节。

## 二、A 轮：原始 starter 基线（mock）

### 运行命令

```bash
# 原始代码在独立检出里（git worktree at 56f7a1f），不影响工作区
cd C:\Users\孙福琳\moneki-baseline\starter
.venv\Scripts\python -m kbqa.rebuild
.venv\Scripts\python -m uvicorn kbqa.server:app --host 127.0.0.1 --port 8001

# 仓库根目录
python eval/run_eval.py --base-url http://localhost:8001 \
  --questions eval/public_questions.jsonl \
  --out eval/runs/starter-baseline-mock
```

### 配置

| 项 | 值 |
|---|---|
| commit | `56f7a1f6601653b5f6c7108ff6db93c65933c6da`（作业包初始提交） |
| 是否配置了 Key | 否 | 
| `llm_mode` | `mock` |
| `/api/health` 快照 | `kb_docs: 36`、`kb_chunks: 53`、`valid_sales_rows: 18628`、`data_period.end: "N/A"` |

### 得分

**17.00 / 100.00（17.0%）**

| 类别 | 得分 | 满分 | 比例 |
|---|---|---|---|
| 指标接口（`metrics`） | 1.00 | 6.00 | 16.7% |
| 检索质量（`retrieval`） | 6.00 | 15.00 | 40.0% |
| 纯数据问题（`data`） | 0.00 | 12.00 | 0.0% |
| 纯文档问题（`doc`） | 0.00 | 16.00 | 0.0% |
| 版本与时效（`version`） | 0.00 | 6.00 | 0.0% |
| 数据 + 文档（`hybrid`） | 0.00 | 18.00 | 0.0% |
| 多轮追问（`multi_turn`） | 1.00 | 9.00 | 11.1% |
| 拒答（`refusal`） | 6.00 | 8.00 | 75.0% |
| 安全（`safety`） | 3.00 | 9.00 | 33.3% |
| 健康检查（`health`） | 0.00 | 1.00 | 0.0% |

## 三、B 轮：为什么这一轮不算真实模型基线

这一轮我按契约 §7.1 把服务切到了官方接口（`LLM_BASE_URL=https://api.deepseek.com`、`LLM_MODEL=deepseek-flash`），
用环境里已有的 Key。结果**每道问答题都在约 1 秒内返回**，分数 13.00，比 mock 还低 4 分。

追下去发现原因：**环境里那个 Key 对 `api.deepseek.com` 是无效的**。直接打官方接口复现：

```
POST https://api.deepseek.com/chat/completions
→ HTTP 401
{"error":{"message":"Authentication Fails, Your api key: ****4676 is invalid ...",
          "type":"authentication_error","code":"invalid_request_error"}}
```

所以这一轮实际测的是「live 模式下 Key 无效时会发生什么」，不是「starter 接上真实模型会怎么样」。
分数下降的 4 分也完全由这个原因解释：mock 模式至少还会走模板回答（S03 安全题答对、拿到 3 分），
而 live 模式下每个请求都 401，全部降级成 `refusal`，那 4 分就丢了。

**因此 13.00 不作为基线，也不会拿它和最终版本比较。** 真实模型基线要等一个可用的 Key（见第六节）。

不过这一轮并非没有收获，它意外验证/暴露了三件事：

1. **契约 §7.3「任何错误码都不能让 `/api/chat` 返回 500」这一条，starter 是过的。** 日志里每个 `POST /api/chat` 都是 `200 OK`，
   错误被包成了结构化 `refusal`，服务没有崩、没有挂起。
2. **但也仅止于此：`refusal` 的文案里写了「接口返回错误码 401」，而 401 是个数字。**
   评测的 `numbers_none_beyond_question` 直接判红——契约 §5 要求拒答时「不得出现编造的数字」，问句里没有 401。
   S02、S03 两道题就是丢在这里。
3. **我当前的第一关代码里是同一句措辞**（`starter/kbqa/service.py:282` 的 `"接口返回错误码 %s" % exc.status`），
   也就是说我继承了同一个缺陷。已记入待修清单（第六节），修的时候要先写一个能复现它的测试。

## 四、C 轮：第一关结束时的得分（mock）

### 运行命令

```bash
cd starter
.venv\Scripts\python -m uvicorn kbqa.server:app --host 127.0.0.1 --port 8000

python eval/run_eval.py --base-url http://localhost:8000 \
  --questions eval/public_questions.jsonl \
  --out eval/runs/gate1-current
```

### 配置

| 项 | 值 |
|---|---|
| commit | `3977bd7aca981239070d216d815308cdf3eeabdf`（本地 `main`） |
| 是否配置了 Key | 否 |
| `llm_mode` | `mock` |
| `/api/health` 快照 | `kb_docs: 35`、`kb_chunks: 95`、`valid_sales_rows: 18290` |

### 得分

**44.50 / 100.00（44.5%）**，27 题全绿 / 共 55 题。每题耗时中位数 0.02 秒、最大 0.07 秒。

| 类别 | 得分 | 满分 | 比例 |
|---|---|---|---|
| 指标接口（`metrics`） | 6.00 | 6.00 | **100.0%** |
| 健康检查（`health`） | 1.00 | 1.00 | **100.0%** |
| 纯数据问题（`data`） | 12.00 | 12.00 | **100.0%** |
| 拒答（`refusal`） | 8.00 | 8.00 | **100.0%** |
| 检索质量（`retrieval`） | 8.00 | 15.00 | 53.3% |
| 多轮追问（`multi_turn`） | 3.50 | 9.00 | 38.9% |
| 安全（`safety`） | 3.00 | 9.00 | 33.3% |
| 数据 + 文档（`hybrid`） | 3.00 | 18.00 | 16.7% |
| 纯文档问题（`doc`） | 0.00 | 16.00 | 0.0% |
| 版本与时效（`version`） | 0.00 | 6.00 | 0.0% |

### 与 A 轮的逐项对比

| 类别 | A（原始） | C（第一关后） | 变化 |
|---|---|---|---|
| `metrics` | 1.00 / 6 | **6.00 / 6** | **+5.00** |
| `health` | 0.00 / 1 | **1.00 / 1** | **+1.00** |
| `data` | 0.00 / 12 | **12.00 / 12** | **+12.00** |
| `refusal` | 6.00 / 8 | 8.00 / 8 | +2.00 |
| `retrieval` | 6.00 / 15 | 8.00 / 15 | +2.00 |
| `multi_turn` | 1.00 / 9 | 3.50 / 9 | +2.50 |
| `safety` | 3.00 / 9 | 3.00 / 9 | 持平 |
| `hybrid` | 0.00 / 18 | 3.00 / 18 | +3.00 |
| `doc` | 0.00 / 16 | 0.00 / 16 | 持平 |
| `version` | 0.00 / 6 | 0.00 / 6 | 持平 |
| **合计** | **17.00** | **44.50** | **+27.50** |

`metrics` 与 `health` 拿满，说明第一关「指标 API 与口径一致」这一项达成了：
其中 M01 期望的 6 月数字是 `net_revenue 156757.00 / refund_amount 953.00 / orders 4311 / qty 6496 / aov 36.36`，
与本实现算出来的完全一致。
`data` 从 0 分到满分也是同一条因果链——那 6 道题答不对正是因为指标口径算错了。

## 五、从基线里看到的第二关线索（先记下来）

**1. 检索类失败得很可疑：多道不同的检索题返回了完全相同的 5 篇文档。**

| 题 | 问的是什么 | top-5 返回的 doc_id |
|---|---|---|
| R04 | 三文鱼那次断供供应商赔了多少钱 | `KB-001, KB-002, KB-003, KB-062, KB-020` |
| R05 | 发票怎么开 | `KB-001, KB-002, KB-003, KB-062, KB-020` |
| R13 | 台风那天几点提前闭店 | `KB-001, KB-002, KB-003, KB-062, KB-020` |
| R15 | 员工折扣几折，能不能和活动叠加 | `KB-001, KB-002, KB-003, KB-062, KB-020` |

四道毫不相关的问题返回**逐字相同**的结果，这不像检索，更像返回了一个固定集合。第二关优先查这条。

**2. 索引只收了 25 篇文档（应有 35 篇）**，`kb_docs` 却报 36——两个方向都错：
少收的是 `.txt` 与 `.html`（`loader.py` 的 `SUPPORTED_SUFFIXES` 只认 `.md`），多报的是把没有 KB 编号的 `README.md` 也数了进去。

**3. `doc` 类 8 题全灭（0/16）**，失败项集中在 `answer_type_in` 与 `cite_all`。

**4. 有一道拒答题编了数字**（`numbers_none_beyond_question`），见第三节第 2 条。

## 六、下一步

1. **需要你提供一个可用的 Key。** 环境里的 `DEEPSEEK_API_KEY` 对 `api.deepseek.com` 返回 401，
   真实模型的基线和最终得分都测不了。三个选择：
   - 你给一个可用的 DeepSeek Key（推荐，契约 §7.1 就是按官方接口设计的）；
   - 或者你指定别的厂商/网关，我按契约 §7.2 的四条改配置（**不改代码**）再跑；
   - 或者接受「最终得分用无 Key 的降级模式」，并在报告里写明——但这样第三关会按降级模式给分。
   在此之前第三关的开发可以用 `eval/llm_gateway.py preflight`（不花钱、不需要 Key）先把接入正确性验完。
2. **进第二关**：先跑一次 `--only retrieval` 缩小范围，按线索 1 查检索为什么返回固定集合；
   每个缺陷都按作业要求走「**先加一个会红的测试，再修**」的提交顺序，逐条写进 `DEBUG_LOG.md`。
3. **记入待修清单**（等做到对应关卡时先写复现测试）：
   - `refusal` 文案里带 HTTP 状态码数字 → 违反契约 §5，`starter/kbqa/service.py:282`。
