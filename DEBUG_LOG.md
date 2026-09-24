# 调试日志

接手 starter 之后发现的缺陷，一条一张表。
每条都按「先加一个会红的测试，再修」的顺序做，所以「回归测试」一栏写的是**真实存在的测试名**，
并且附上它在修复前确实是红的证据。

分数线（公开题库 100 分，无 Key 的 mock 模式）：

| 阶段 | 得分 | 检索类 | 多轮追问 |
|---|---|---|---|
| 原始 starter（`56f7a1f`） | 17.00 | 6 / 15 | 1.0 / 9 |
| 第一关结束（`3977bd7`） | 44.50 | 8 / 15 | 3.5 / 9 |
| 第二关 · 分词 + 命中标注 + 测试替身（D1–D3） | 49.00 | 14 / 15 | 3.5 / 9 |
| 第二关 · 规划 + 版本 + 会话（D5、D8–D12） | **70.00** | **14 / 15** | **9.0 / 9** |

---

## D1 · 分词器不切中文，BM25 对所有查询都返回 0 分

| 项 | 内容 |
|---|---|
| **现象** | 公开评测里 R04、R05、R13、R15 四道毫不相关的检索题返回了**逐字相同**的 top-5：`KB-001#1, KB-002#1, KB-003#1, KB-062#1, KB-020#1`；`retrieval` 只有 6/15。另外 `/api/retrieve` 里每一段的 `score` 都恰好是 `0.0000`。 |
| **假设** | ① 先猜是「先取 top_k 再按元数据过滤」的顺序反了——评测说明里专门点了这个坑。**排除**：顺序问题只会让结果条数变少，不会让四道不同的问题返回完全相同的一组文档。<br>② 再猜是元数据过滤把候选清空了，只好走补齐逻辑。**排除**：把 `SearchResult.filtered` 打出来看，被排除的只有版本替换链上的少数文档，远不至于清空候选。<br>③ 于是转向「为什么结果不随问题变化」：`score` 全是 0 说明**一个查询词元都没命中**，问题出在打分之前。 |
| **验证** | 直接调分词器与索引：<br>`tokenize("三文鱼那次断供供应商赔了多少钱")` → `['三文鱼那次断供供应商赔了多少钱']`，**整句一个词元**。<br>索引里最长的词条长 **103 个汉字**（`'号开门前二十分钟,我照例试了一下收银,刷卡和扫码全线连不上…'`）。<br>`[t for t in index.postings if t in tokenize(q)]` → `[]`，命中数为零。<br>反证：返回的那 5 条恰好是 `score=0` 且被标了 `padded` 的补齐片段——补齐逻辑按索引顺序每篇取第一段，所以固定是前 5 篇文档。 |
| **根因** | `starter/kbqa/tokenizer.py:22`：`tokenize()` 实现为 `normalise(text).split()`——按空白切词。中文不写空格，整句话成了一个词元，文档侧同样如此，查询与索引没有任何共同词元。 |
| **修复** | commit `fix(tokenizer): 中文按字符二元组切分，恢复 BM25 打分`。<br>改成按字符类型分段：汉字走重叠二元组（`退款政策` → `退款`/`款政`/`政策`），字母数字及夹在其中的 `- _ . / :` 整段保留（`2026-07-04`、`kb-022`）。<br>`TOKENIZER_VERSION` 由 `tokenizer-2` 提到 `tokenizer-3`，缓存键里含版本号，索引缓存自动失效（实测缓存键从 `8651fac326e2` 变为 `9107a0e0e818`）。<br>选二元组而非分词词典的理由：评审会整份替换 `knowledge_base/`，二元组不需要词典就能覆盖任意新词。 |
| **回归测试** | `tests/test_tokenizer.py`（17 项）。修复前：**13 failed / 4 passed**。核心两条是 `test_query_terms_hit_the_index`（7 条真实问句每条都要能在索引里命中）与 `test_index_terms_are_short_enough_to_match`（索引里不得出现 3 个以上连续汉字的词元）。<br>修复后 `retrieval` 从 8/15 升到 14/15。 |

## D2 · 命中的 `doc_id` 被换成别的文档

| 项 | 内容 |
|---|---|
| **现象** | 修完 D1 后检索结果变相关了，但结果里出现自相矛盾的行：`doc_id=KB-053` 而 `chunk_id=KB-051#2`；`doc_id=KB-014` 而 `chunk_id=KB-024#1`。而且呈现**链式**错位：`KB-014→KB-024#1`、`KB-024→KB-023#2`、`KB-023→KB-060#5`。 |
| **假设** | ① 先猜是索引缓存与内存里的 chunk 列表不一致（缓存是上一次构建留下的）。**排除**：重建索引后现象不变。<br>② 再猜有重复 `chunk_id` 导致按 `chunk_id` 建字典时互相覆盖。**排除**：`len(chunks)=95`、去重后仍是 95。<br>③ 转向「错位为什么会传递」：链式错位的形状说明是**下标落后**，去看拼接结果的那几行。 |
| **验证** | 写 `tests/test_retriever.py`，断言每条命中的 `doc_id` 等于自己 `chunk_id` 的前缀，以及 `hit.text` 就是该片段正文。8 道真实问句里 **6 道红**，报出的错位正是上面那几条链。 |
| **根因** | `starter/kbqa/retriever.py:276`：`hit.doc_id = ordered[len(hits)].doc_id`。<br>`hit` 是 `_hit(position, ...)` 造出来的（`chunk_id`、`text` 都取自那个片段），却把 `doc_id` 换成了 `ordered[len(hits)]`——也就是**排序里第 `len(hits)` 个**片段所属的文档。只要上面因为「每篇文档只占一格」而 `continue` 跳过一个片段，`len(hits)` 就落后于循环下标，此后每条命中的 `doc_id` 都指向别的文档。<br>评测是按 `doc_id` 对金标文档的，所以即使排序完全正确，`/api/retrieve` 的得分也是错的。 |
| **修复** | commit `fix(retriever): 命中的 doc_id 必须与自身 chunk_id 同源`。<br>删掉那行覆盖，直接 `hits.append(self._hit(position, score, filtered))`——`_hit` 已经把 `doc_id`/`chunk_id`/`text` 都从同一个片段取好了。`ordered` 列表随之成为死代码，一并删除。 |
| **回归测试** | `tests/test_retriever.py::test_hit_doc_id_matches_its_chunk`、`::test_hit_text_belongs_to_the_same_chunk`。修复前 8 道题里 6 道红。 |

## D3 · 测试替身打在类上且不还原，检索相关的测试全部跑在假数据上

| 项 | 内容 |
|---|---|
| **现象** | `tests/test_retriever.py` **单独跑是绿的，全量 `pytest tests` 跑却有 8 条红**。同一份代码、同一份数据，只因为跑法不同结论就相反。 |
| **假设** | ① 先怀疑索引缓存：全量跑时别的测试先动了缓存。**排除**：给测试单独指定 `VAR_DIR` 后现象不变。<br>② 再怀疑 chunk 重复。**排除**（见 D2）。<br>③ 注意到「单独跑绿、一起跑红」是典型的**顺序相关**，去看 `conftest.py` 里对检索做了什么。 |
| **验证** | 交换测试文件顺序重跑：`pytest tests/test_retriever.py tests/test_api.py` 绿，`pytest tests/test_api.py tests/test_retriever.py` 红——确认与执行顺序有关。<br>再看红的是哪些断言：`test_hit_doc_id_matches_its_chunk` 反而不红（假数据的 `doc_id`/`chunk_id` 恰好自洽），红的是 `test_hit_text_belongs_to_the_same_chunk`（假数据返回的是一段写死的 `FAKE_TEXT`，当然不在索引里）。 |
| **根因** | `starter/tests/conftest.py:50`：`retriever_module.Retriever.search = fake_search`——替身打在 **`Retriever` 类**上，而且 fixture 只在建立时替换、**从不还原**。`client` 是 session 级 fixture，所以 `test_api.py` 一跑，整个 session 里所有 `Retriever` 实例的 `search` 都成了那份固定返回。<br>这条同时解释了一个更值得注意的事：交接文档写着「测试全部通过」，但**测试把检索整个换成了固定返回**，所以检索类的缺陷它一个都抓不到——「绿灯」和「检索是对的」之间没有关系。 |
| **修复** | commit `test(conftest): 检索替身只替换 API 用的 Service 实例`。<br>改为 `server.service().retriever.search = fake_search`（实例属性遮蔽类方法，别的 `Retriever` 实例不受影响）。替身函数相应去掉 `self` 参数——实例属性不会被绑定。 |
| **回归测试** | `tests/test_retriever.py::test_real_retriever_is_not_replaced_by_the_api_stub` 做守卫；并交换文件顺序重跑确认不再依赖执行次序。全量：**126 passed**。 |

---

## D5 · 兜底路由把已经判对的问题推翻，「多少/多久/几」一律当成取数题

| 项 | 内容 |
|---|---|
| **现象** | `doc` 类 8 题全灭（0/16），`version` 类 0/6。逐题跑规划器，11 道题里判错 6 道，且分成两种清晰的形状：<br>① C01「外卖订单多久内可以申请退款？」、C04「供应商最后赔了我们多少钱？」、C08「员工迟到多久算一次？」、V01「618 活动价多少？」→ 全被判成 `intent=data kind=summary`；<br>② C03「Super Souper 现在周五晚上营业到几点？」、V02「会员现在单笔充值满 500 送多少？」→ 被判成 `refusal / out_of_period`，理由是「数据库里只有 2026-05-01 至 2026-08-31 的销售明细，2026-09-01 至 2026-09-01 没有任何数据」。 |
| **假设** | ① 先猜是关键词表漏了词，去补 `POLICY_WORDS`。**排除**：`POLICY_WORDS` 里**本来就写着「多久」和「几点」**，说明作者的意图就是「问时长、问钟点属于问规定」。<br>② 那就是有东西在**后面**把它推翻了。往上翻 `_choose_kind`，末尾果然有一段兜底路由，与 `POLICY_WORDS` 的意图正好相反。<br>③ 至于第②种形状：文档问题被判成取数题之后，`_check_period` 就会拿「今天」去比数据区间，而今天的 2026-09-01 本来就在销售明细之外——**拒答是上游误判的下游后果**，不是独立缺陷。 |
| **验证** | ① 读代码定位到 `planner.py:251-258`：这段「路由」跑在上面全部判断**之后**，无条件把 `intent` 改成 `data`、把 `kind` 里的 `doc/anomaly/target/price` 改成 `summary`。<br>② 做对照实验：把这一整段删掉再跑规划器，**11 道题全部判对了**。原来担心「牛肉poke 六月一共卖了多少钱」「味噌拉面 7 月卖了多少碗」这类没有显式指标词的题会失去兜底——检查发现 `METRIC_WORDS` 里早有「卖了多少钱」「多少碗」，它们走的是正常分支，**根本不依赖这段兜底**。<br>③ 反证它还在害人：删掉之后「S03 六月第二周营业额为什么这么低」（README 里的旗舰例子）从被强制成 `doc` 变成了正确的 `hybrid/anomaly`——原来「为什么」那一支会把数据库那一半丢掉。<br>④ 关于「两边都走一遍太慢」：`needs_data`/`needs_docs` 由 kind 与 intent 决定，只有 hybrid 两边都走，删掉这段并不会让取数题多跑一遍检索。 |
| **根因** | `starter/kbqa/planner.py:251-258`。它同时踩了两类：既与 `POLICY_WORDS`（含「多久」「几点」）互相矛盾，又把 `anomaly`/`target`/`price` 这些**本来就该 hybrid** 的类别压成纯取数。 |
| **修复** | commit `fix(planner): 删掉推翻已判结果的兜底路由`。整段替换为一段说明，路由只由上面那串有依据的判断决定。 |
| **回归测试** | 新增 `tests/test_planner.py`（23 项）：17 道真实问题按主语断言 `intent`，外加「文档问题不该被判成区间外拒答」与「『多久』单独不足以判定为取数题」。修复前 **12 failed / 11 passed**。<br>`doc` 仍为 0（回答层的问题，见 D4），但 `hybrid` 从 3.00/18 升到 **18.00/18**，总分 49.00 → **64.50**。 |

## D8 · 版本过滤从未生效：`meta()` 写 `state`，读的人读 `status`

| 项 | 内容 |
|---|---|
| **现象** | C01「外卖订单多久内可以申请退款？」回答的正文是 **`KB-012 退款政策 v1`**，开头就写着「本版本已废止，现行版本见 KB-013」；而今天 2026-09-01，v1 自 2026-06-15 起就被 v2（KB-013）取代了。契约明确要求「文档有新旧版本时，用当前有效的那一版」。 |
| **假设** | ① 先猜 `_eligible()` 的日期比较写反了。**排除**：把 `SearchResult.filtered` 打出来，**它是空的**——过滤逻辑一条都没触发，不是比较方向的问题。<br>② 再看 `_effective_to` 的构建：它明明建立起了 `{'KB-002': '2026-05-01', 'KB-010': '2026-07-01', 'KB-012': '2026-06-15'}` 三条取代关系。说明 `superseded_by` 读得到，那问题就在同一个判断里的另一个条件上。 |
| **验证** | 把 `docs_meta` 的键打印出来：<br>`meta["state"] = '已废止'`，而 `meta["status"] = None`。<br>再统计全部文档：`state` 取值是 `{'现行': 27, '归档': 5, '已废止': 3}`，`retriever.py:120` 判的条件是 `meta.get("status") == "已废止"`——`None == "已废止"` 恒为假。<br>顺带查出第二个受害者：`docfacts.version_note()` 也读 `meta.get("status")`，所以引用里的版本说明（「2026-06-15 起生效，已由 KB-013 取代」）从来没能显示过。 |
| **根因** | 产出方 `starter/kbqa/loader.py:75` 写的是 `"state": self.status`，消费方 `starter/kbqa/retriever.py:120` 与 `starter/kbqa/docfacts.py:277` 读的都是 `"status"`。字典 `.get()` 取不到键只返回 `None`，不抛异常、不报错——**这个键名错配让「已废止的版本要挡掉」这个条件从来没有成立过**。 |
| **修复** | commit `fix(loader): meta() 的版本状态键与读它的地方对齐`。把 `"state"` 改成 `"status"`（grep 确认没有任何地方读 `"state"`，改产出方是安全的），并加测试守住「meta() 写出的键必须等于读它的地方读的键」。 |
| **回归测试** | `tests/test_retriever.py::test_meta_exposes_the_status_key_its_readers_use`、`::test_superseded_versions_are_filtered_out`、`::test_no_superseded_version_in_current_results`（对 8 道真实问题断言结果里不出现任何带 `superseded_by` 的文档）、`::test_historical_question_still_reaches_the_old_version`（反向：问「以前那一版」时必须取得到）。修复前 4 项红（`KB-012`、`KB-010` 混在结果里）。 |

## D9 · 「重建命令」其实没重建；缓存键不含 loader 的输出格式

| 项 | 内容 |
|---|---|
| **现象** | 修完 D8 的键名后跑 `python -m kbqa.rebuild`，再跑测试**仍然全红**。读 `.cache/index.json` 发现里面的元数据键**还是 `state`**——重建写了半天，缓存里是旧的。 |
| **假设** | ① 先猜 `save_index` 没写成功。**排除**：缓存文件的 mtime 就是刚才。`build_index()` 在内存里构建的结果里键已经是 `status`。<br>② 那就只能是**写进去的不是内存里那份**——去读 `rebuild.py` 的调用。 |
| **验证** | `rebuild.py:27`：`index = load_index(settings.kb_dir, settings.index_path)`——`load_index` 的 `rebuild` 参数默认是 `False`，于是它命中缓存、把旧的索引对象原样返回，`save_index` 根本没被调用。打印缓存键，重建前后都是 `9107a0e0e818`，与代码改动无关。<br>再查缓存键的构成：`content_key()` 只哈希了 `INDEX_VERSION / CHUNKER_VERSION / TOKENIZER_VERSION` **与知识库文件内容**。改了 loader 的输出格式，这两样都没变，缓存自然不失效。 |
| **根因** | 两个：<br>① `starter/kbqa/rebuild.py:27` 漏传 `rebuild=True`，契约 §8 要求的「从这两个目录重新生成清洗后的数据和检索索引」并没有真正做到，只是「按缓存判断要不要算」。<br>② `starter/kbqa/index.py::content_key()` 少了一个维度——loader 的输出格式（元数据的键、支持的格式），导致只改 loader 时缓存不失效。 |
| **修复** | commit `fix(rebuild): 重建命令真正重建，并把 loader 版本纳入缓存键`。<br>`load_index(..., rebuild=True)`；新增 `loader.LOADER_VERSION = "loader-2"` 并纳入 `content_key()`。缓存键随之变化，旧缓存自动失效。 |
| **回归测试** | 由 D8 那组测试间接守住：键名修好但缓存不失效时它们仍然是红的，重建命令修好之后才转绿。`test_meta_exposes_the_status_key_its_readers_use` 直接读文件、不经过缓存，用来区分「文件读错了」和「缓存是旧的」这两种可能。 |

## D10 · 先按 top_k 截断再按元数据过滤，结果少给

| 项 | 内容 |
|---|---|
| **现象** | D8 修好、版本过滤第一次真正生效之后，`/api/retrieve` 对「外卖订单多久内可以申请退款」只返回 **4 条**，而契约 §4 要求索引片段足够时**恰好** `top_k` 条。 |
| **假设** | 这是 D8 的**下游后果**：过滤以前是空转，所以从没暴露过。「只剩三四条」正是评测说明里点名的那种形状——先取前 `top_k`、再过滤。 |
| **验证** | 读 `search()`：候选池 `allowed = set(range(len(self.index.chunks)))` 是**全部**片段，被排除的文档照样参与打分、照样占前排名额；而过滤是最后一行 `hits = [hit for hit in hits if hit.doc_id not in excluded]`，在补齐到 `top_k` **之后**才执行。<br>实测：4 条，且被挡掉的 `KB-012`/`KB-010` 都在补齐后又被删掉了。 |
| **根因** | `starter/kbqa/retriever.py`：候选池没有先按元数据过滤，过滤又排在截断之后。顺序反了。 |
| **修复** | commit `fix(retriever): 先过滤再截断，保证恰好 top_k 条`。`allowed` 改为「通过元数据过滤的那些片段」，过滤后的 `hits` 那一步保留为兜底（正常情况下是空操作）。 |
| **回归测试** | `tests/test_retriever.py::test_returns_exactly_top_k`，对 8 道真实问题断言恰好 5 条。修复前红（实测 4 条）。 |

## D11 · 会话历史没传给规划器，追问一律被当成孤立提问

| 项 | 内容 |
|---|---|
| **现象** | V03 第 2 轮「那 6 月的时候呢？」收到的回答是「这句像是追问，但这个会话里没有上文。请把问题补完整……」，`answer_type=clarify`；T01 第 2 轮「那 7 月呢？」同样。而同一 `session_id` 的上一轮刚刚答对过。`multi_turn` 只有 3.50/9。 |
| **假设** | ① 先猜会话存储没记下来。**排除**：`test_history_is_actually_recorded` 直接查 `sessions.history()`，是有内容的。<br>② 再猜追问还原的逻辑本身不会做。**排除**：把历史**显式**传给 `planner.plan(question, history)`，`standalone` 正确补全——说明规划器没问题。<br>③ 那就是两者之间的接线断了。 |
| **验证** | `starter/kbqa/service.py:156`：`plan = self.planner.plan(question)`——**少传了 `history`**。上一行刚把 `history` 取出来，下一行就忘了传。规划器里 `followups.resolve(question, history or [])` 于是永远拿到空列表，`if not history and looks_like_follow_up(...)` 成立，短句直接反问。 |
| **根因** | `starter/kbqa/service.py:156`（原行号）。 |
| **修复** | commit `fix(service): 把会话历史传给规划器`。一行：`plan = self.planner.plan(question, history)`。 |
| **回归测试** | `tests/test_chat_session.py::test_follow_up_keeps_the_topic`（同一会话里第二句不能是 `clarify`）、`::test_sessions_do_not_bleed_into_each_other`、`::test_planner_receives_the_history`。`multi_turn` 从 3.50/9 升到 **9.00/9**。 |

## D12 · 会话存储完全忽略 `session_id`

| 项 | 内容 |
|---|---|
| **现象** | 修完 D11、给规划器传了历史之后，`test_sessions_do_not_bleed_into_each_other` 立刻转红：**另一个 `session_id` 里也读到了第一段的对话**。契约 §5 明确「不同 `session_id` 之间不能串线」。 |
| **假设** | D11 之前所有追问都回 `clarify`，这条串线被掩盖住了：既然没有一次追问被认真处理，也就看不出历史是混在一起的。传了历史之后它才浮出来。 |
| **验证** | 读 `sessions.py`：`self._turns` 是**一条平铺列表**，`history(session_id)` 返回 `list(self._turns)`、`append(session_id, turn)` 也是直接 append——**两个方法都没看 `session_id`**。三个后果：<br>① 不同会话互相串线；<br>② `max_turns` 那个「最近几轮」的窗口变成全局的，一个人的追问会把另一个人的上文挤掉；<br>③ 构造参数 `max_sessions` 从头到尾没被用过。 |
| **根因** | `starter/kbqa/sessions.py:12-28`：数据结构本身就没有按会话分区。 |
| **修复** | commit `fix(sessions): 会话历史按 session_id 分开存`。改成 `dict[session_id, list[turn]]`，每个会话各自保留最近 `max_turns` 轮，另用一条最近使用顺序在超过 `max_sessions` 时淘汰最久未用的那个；没带 `session_id` 的请求不留历史（没有「同一段对话」可言，也不该串到别人身上）。 |
| **回归测试** | `tests/test_chat_session.py` 里 4 项存储层测试：会话隔离、每会话各自的轮次窗口、会话数上限与淘汰、无 `session_id`。修复前 **5 failed**。 |

---

## 待修（还没处理）

| # | 现象 | 定位 |
|---|---|---|
| D4 | 「帮我把 S01 的销售记录全部删掉」这类**破坏性请求**没有拒答，反而把检索到的 `KB-030 门店档案` **原文整段当答案吐出来**，`answer_type` 填成 `doc`，还带出 128、105、42 等问句里没有的数字（违反契约 §5「refusal 不得出现编造的数字」）。 | 回答层缺少破坏性意图的拦截；且存在「把整段文档当答案」的兜底路径。 |
| D6 | R04「三文鱼那次断供供应商赔了多少钱」期望命中英文邮件 `KB-022`（现为 14/15 里唯一未过的检索题）。中文问句与英文正文没有共同词元，靠的是别名词典把 `salmon` 桥接到「三文鱼poke」。 | `kbqa/aliases.py` 与 `retriever.py` 的 `DOC_PRIOR` 机制。 |
| D7 | 模型出错时 `refusal` 文案写成「接口返回错误码 401」，401 是个数字，被评测的 `numbers_none_beyond_question` 判红。 | `starter/kbqa/service.py:282`（我沿用了 starter 的措辞，需一并改掉）。 |
| D13 | `doc` 类仍 0/16：回答正文常常**就是检索到的那一段原文**（例如把「门店档案 S02」整张表当地过敏原的答案），而且 `citations` 列出的 `doc_id` 与正文来源**不是同一篇**（V02 正文是 KB-011 的内容，`citations` 却是 KB-051/KB-013）。 | 回答层：`answerer.py` 的兜底路径与 `docfacts` 出具引用的那一步。 |
| D14 | `version` 类 2/6。第 1 轮正文用对了版本（V02 正文就是 KB-011 v2 的内容），但 `citations` 指错了文档；第 2 轮（问「6 月当时」）已经能取到 KB-010 v1。 | 同 D13。 |

## 一次无效的测量（记下来提醒自己）

D11/D12 修完先跑了一次评测，分数停在 64.50 不动，我一度以为修复无效。查下去发现是**评测打到了旧服务**：
新起的 uvicorn 因为 8000 端口还被上一个进程占着，绑定失败（日志里 `[Errno 10048]`），而评测脚本照常连上了那个**没有新代码**的旧进程。
停掉旧进程、确认日志里有 `Application startup complete` 之后重跑，分数才是 70.00。

教训写进流程：起服务之后要确认**确实绑上了**（看日志），而不是只看「命令返回了」。

