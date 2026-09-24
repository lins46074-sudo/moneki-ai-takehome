"""检索器测试。

守的是 `/api/retrieve` 返回值的基本自洽性：一条命中里的 `doc_id`、`chunk_id`、`text`
必须来自**同一个片段**。评测按 `doc_id` 对金标文档，一旦三者不是同一篇文档，
打分就全是错的——哪怕排序本身是对的。

`retriever.py` 里 `hit.doc_id = ordered[len(hits)].doc_id` 这一行会把
`doc_id` 换成另一个片段所属的文档：只要循环里跳过一个片段（「每篇文档只占一格」触发时），
`len(hits)` 就落后于循环下标，从此每条命中的 `doc_id` 都错位。
"""

from __future__ import annotations

import pytest

from kbqa.config import load_settings
from kbqa.index import load_index
from kbqa.loader import load_knowledge_base
from kbqa.retriever import Retriever

QUERIES = [
    "三文鱼那次断供供应商赔了多少钱",
    "发票怎么开",
    "台风那天几点提前闭店",
    "员工折扣几折，能不能和活动叠加",
    "外卖订单多久内可以退款",
    "冷萃乌龙茶首月的目标销量是多少",
    "S04 为什么不卖吞拿鱼三明治了",
    "会员单笔充值满 500 送多少",
]


@pytest.fixture(scope="module")
def retriever():
    settings = load_settings()
    return Retriever(load_index(settings.kb_dir, settings.index_path, rebuild=False), settings.today)


def test_meta_exposes_the_status_key_its_readers_use():
    """`Document.meta()` 写出的键必须和读它的地方一致。

    `retriever._eligible()` 与 `docfacts.version_note()` 读的都是 `meta["status"]`，
    而 `meta()` 曾经把它写成 `"state"`。字典 `.get()` 拿不到键只返回 `None`，
    不报错，于是「已废止的版本要挡掉」这个条件**从来没有成立过**，
    引用里的版本说明也从来没显示过。
    """
    settings = load_settings()
    documents, _ = load_knowledge_base(settings.kb_dir)
    assert documents, "知识库里应该读得到文档"
    for document in documents:
        meta = document.meta()
        assert meta.get("status") == document.status, (
            "%s 的 meta() 里读不到 status（拿到 %r，文档本身是 %r）"
            % (document.doc_id, meta.get("status"), document.status)
        )


def test_superseded_versions_are_filtered_out(retriever):
    """问「现在」的规定时，已废止的版本不能出现在结果里。

    KB-012（退款政策 v1）自 2026-06-15 起被 KB-013（v2）取代，今天 2026-09-01，
    所以答案只能是 KB-013。
    """
    result = retriever.search("外卖订单多久内可以申请退款？", top_k=5)
    doc_ids = [hit.doc_id for hit in result.hits]
    assert "KB-013" in doc_ids, "现行版本没有出现在结果里：%s" % doc_ids
    assert "KB-012" not in doc_ids, "已废止的版本混进了结果：%s" % doc_ids
    assert "KB-012" in {item["doc_id"] for item in result.filtered}, (
        "被挡掉的版本要写进 filtered，说明为什么挡：%s" % result.filtered
    )


@pytest.mark.parametrize("query", QUERIES)
def test_no_superseded_version_in_current_results(retriever, query):
    """不挑题目：任何「现在」的问题都不该命中带 `superseded_by` 的文档。"""
    superseded = {
        doc_id
        for doc_id, meta in retriever.index.docs_meta.items()
        if meta.get("superseded_by")
    }
    assert superseded, "知识库里应该有被取代的版本，否则这条测试没有意义"
    leaked = [
        hit.doc_id for hit in retriever.search(query, top_k=5).hits if hit.doc_id in superseded
    ]
    assert leaked == [], "%s 的结果里混进了已废止的版本：%s" % (query, leaked)


def test_historical_question_still_reaches_the_old_version(retriever):
    """问「以前那一版」时，已废止的文档必须能取回来——它本身就是答案。"""
    result = retriever.search("以前的退款政策是怎么规定的？", top_k=5)
    doc_ids = [hit.doc_id for hit in result.hits]
    assert "KB-012" in doc_ids, "问旧版时取不回旧版：%s" % doc_ids


def test_chinese_query_can_reach_an_english_document(retriever):
    """跨语言的桥：中文问句问「三文鱼」，英文邮件里写的是 `salmon`。

    别名机制把英文片段归一化到数据库写法，所以 KB-022（那封纯英文的供应商邮件）
    的片段里会出现「三文」「文鱼」两个词元——中文问句才可能命中一封英文文档。
    这条是已有能力，不是缺陷；写成测试是为了别在调排序时把它弄丢。
    """
    matched = 0
    for chunk in retriever.index.chunks_of("KB-022"):
        tokens = set(retriever.index._tokens_of(chunk))
        if {"三文", "文鱼"} <= tokens:
            matched += 1
    assert matched > 0, "英文邮件没有被归一化到中文写法，跨语言检索会完全失效"


def test_bridge_only_uses_tokens_from_the_alias_table(retriever):
    """桥接词必须来自别名词典，不能凭空造。`salmon` 指向「三文鱼poke」。"""
    table = retriever.index.aliases
    distinctive = table.distinctive_tokens()
    assert distinctive.get("salmon") == "三文鱼poke"
    assert table.variants("三文鱼poke") == ["三文鱼poke", "鲑鱼波奇饭", "Salmon Poke"]


@pytest.mark.xfail(
    reason="已知限制（DEBUG_LOG D6b）：冷萃乌龙茶的英文别名 Cold Brew Oolong 里的 "
    "cold/brew 都是通用英文词，邮件里的供应商名 Tasman Cold Chain Seafood 也含 cold，"
    "于是这封跟茶毫无关系的邮件被注入了冷萃/乌龙等噪声词元，反过来拉低它自己的 BM25 分数。"
    "修法是把桥接词按语料里的文档频次再筛一道（桥接词不该比对象本身更常见），"
    "属于检索精度优化，不影响 R04 的结论——详见 DEBUG_LOG。",
    strict=False,
)
def test_generic_english_words_do_not_bridge(retriever):
    cold_brew = "冷萃乌龙茶"
    email = "\n".join(chunk.text for chunk in retriever.index.chunks_of("KB-022"))
    assert cold_brew not in retriever.index.aliases.strict_mentions(email)


def test_r04_cross_lingual_case_is_recorded_as_a_known_gap(retriever):
    """R04「三文鱼那次断供供应商赔了多少钱」的现状：期望 KB-022 进前五，实际进不去。

    钉住现状是为了**看着它变**：现在能进前 10，哪天掉出去了说明检索退步了；
    哪天进了前 5，就把这条和上面那条 xfail 一起改掉。原因与量化见 DEBUG_LOG 的 D6。
    """
    result = retriever.search("三文鱼那次断供供应商赔了多少钱", top_k=30)
    ranking = [hit.doc_id for hit in result.hits]
    gold = [index for index, doc_id in enumerate(ranking, 1) if doc_id == "KB-022"]
    assert gold, "KB-022 连前 30 都进不去了，检索明显退步"
    assert min(gold) <= 10, "KB-022 掉出前 10 了：第 %d 名" % min(gold)


def test_real_retriever_is_not_replaced_by_the_api_stub(retriever):
    """守卫：API 测试的检索替身不能污染真实检索器。

    替身以前打在 `Retriever` 类上且不还原，导致本文件里的断言全部跑在假数据上
    （假数据的 doc_id 与 chunk_id 恰好自洽，只有正文会对不上）。
    """
    assert retriever.search.__qualname__.startswith("Retriever."), (
        "真实检索器被替换了：%s" % retriever.search.__qualname__
    )
    assert retriever.search.__func__ is not None


@pytest.mark.parametrize("query", QUERIES)
def test_hit_doc_id_matches_its_chunk(retriever, query):
    """`doc_id` 必须等于 `chunk_id` 的前缀，且正文确实是这个片段的内容。"""
    result = retriever.search(query, top_k=5)
    mismatched = [
        (hit.doc_id, hit.chunk_id)
        for hit in result.hits
        if hit.doc_id != hit.chunk_id.split("#")[0]
    ]
    assert mismatched == [], "doc_id 与自身的 chunk_id 不符：%s" % mismatched


@pytest.mark.parametrize("query", QUERIES)
def test_hit_text_belongs_to_the_same_chunk(retriever, query):
    """命中里的正文必须就是 `chunk_id` 指的那一段，不能是别段的内容。"""
    result = retriever.search(query, top_k=5)
    by_chunk = {chunk.chunk_id: chunk for chunk in retriever.index.chunks}
    for hit in result.hits:
        chunk = by_chunk[hit.chunk_id]
        assert hit.doc_id == chunk.doc_id
        assert hit.text == chunk.text


@pytest.mark.parametrize("query", QUERIES)
def test_hits_are_sorted_by_score(retriever, query):
    """契约 §4：按相关性从高到低排序。"""
    scores = [hit.score for hit in retriever.search(query, top_k=5).hits]
    assert scores == sorted(scores, reverse=True), "命中没有按分数降序：%s" % scores


@pytest.mark.parametrize("query", QUERIES)
def test_returns_exactly_top_k(retriever, query):
    """契约 §4：索引里的片段远多于 top_k 时，必须**恰好**返回 top_k 条。

    排序时如果把会被过滤掉的文档也算进候选，它们就会占掉本该属于现行文档的名额，
    过滤之后结果就少给几条。「先按 top_k 截断、再按元数据过滤」正是这个毛病，
    正确做法是**先把候选池限在可用的片段上，再排序取前 top_k**。
    """
    result = retriever.search(query, top_k=5)
    assert len(result.hits) == 5, "只返回了 %d 条（%s）" % (
        len(result.hits),
        [hit.doc_id for hit in result.hits],
    )


@pytest.mark.parametrize("query", QUERIES)
def test_results_are_distinct_chunks(retriever, query):
    """同一个片段不该在一份结果里出现两次。"""
    chunk_ids = [hit.chunk_id for hit in retriever.search(query, top_k=5).hits]
    assert len(chunk_ids) == len(set(chunk_ids)), "结果里有重复片段：%s" % chunk_ids
