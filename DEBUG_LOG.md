# 调试日志

接手 starter 之后发现的缺陷，一条一张表。
每条都按「先加一个会红的测试，再修」的顺序做，所以「回归测试」一栏写的是**真实存在的测试名**，
并且附上它在修复前确实是红的证据。

分数线（公开题库 100 分，无 Key 的 mock 模式）：

| 阶段 | 得分 | 检索类 |
|---|---|---|
| 原始 starter（`56f7a1f`） | 17.00 | 6 / 15 |
| 第一关结束（`3977bd7`） | 44.50 | 8 / 15 |
| 第二关：分词 + 命中标注 + 测试替身 | 49.00 | **14 / 15** |

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

## 待修（第二关进行中：修掉一层才看得见下一层）

修完 D1 之后检索变准了，反而**暴露**出下一层的两个缺陷。它们不是新引入的，是原来被「检索返回垃圾」掩盖住的：

| # | 现象 | 初步定位 |
|---|---|---|
| D4 | 「帮我把 S01 的销售记录全部删掉」这类**破坏性请求**没有拒答，反而把检索到的 `KB-030 门店档案` **原文整段当答案吐出来**，`answer_type` 填成 `doc`，还带出 128、105、42 等问句里没有的数字（违反契约 §5「refusal 不得出现编造的数字」）。 | 回答层缺少破坏性意图的拦截；且存在「把整段文档当答案」的兜底路径。 |
| D5 | 「7 月顾客投诉最集中的是什么问题？有多少条？」应查知识库 `KB-060`，却被规划成**纯数据问题**，答成了 7 月的营业额指标（`answer_type=data`，`citations` 为空）。 | 规划器把「有多少条」这类措辞一律当成了数据库问题，没有先判断问题的主语是不是文档里的话题。 |

另外已记录、尚未处理的：

| # | 现象 | 定位 |
|---|---|---|
| D6 | R04「三文鱼那次断供供应商赔了多少钱」期望命中英文邮件 `KB-022`（现为 14/15 里唯一未过的检索题）。中文问句与英文正文没有共同词元，靠的是别名词典把 `salmon` 桥接到「三文鱼poke」。 | `kbqa/aliases.py` 与 `retriever.py` 的 `DOC_PRIOR` 机制。 |
| D7 | 模型出错时 `refusal` 文案写成「接口返回错误码 401」，401 是个数字，被评测的 `numbers_none_beyond_question` 判红。 | `starter/kbqa/service.py:282`（我沿用了 starter 的措辞，需一并改掉）。 |
