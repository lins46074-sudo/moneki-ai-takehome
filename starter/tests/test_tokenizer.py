"""分词测试。

这个文件是为一个具体缺陷写的：`tokenize()` 曾经是「按空白切词」。
中文不写空格，所以一句话会被切成**一个**词元——查询词元在索引里一个都命不中，
BM25 对所有查询都返回 0 分，`/api/retrieve` 只好走「凑满 top_k」的补齐逻辑，
于是不同的问题返回了同一组文档。下面这些断言在修复前是红的。

分词粒度按代码里原本的约定走：中文用**字符二元组**。三条旁证：
`retriever.py` 的注释「单字（“月”“日”“店”）在二元组的世界里基本是噪声」、
`docfacts.py` 里 `if len(term) >= 2` 的过滤、以及 `STOP_CHARS` 里
「什么」「怎样」「如何」「多少」「可以」这类**成对**虚词——都只有在词元是
二字时才说得通。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kbqa.config import load_settings
from kbqa.index import load_index
from kbqa.tokenizer import content_tokens, normalise, tokenize

CJK_RANGES = ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF), (0x3040, 0x30FF))


def is_cjk(char: str) -> bool:
    return any(low <= ord(char) <= high for low, high in CJK_RANGES)


def longest_cjk_run(token: str) -> int:
    """词元里最长的一段连续汉字。二元组分词下这个值不该超过 2。"""
    best = current = 0
    for char in token:
        current = current + 1 if is_cjk(char) else 0
        best = max(best, current)
    return best


# -- 中文要被切开 ----------------------------------------------------------------


def test_chinese_sentence_is_not_one_token():
    """中文句子必须切成多个词元；按空白切会只得到 1 个。"""
    tokens = tokenize("三文鱼那次断供供应商赔了多少钱")
    assert len(tokens) > 1, "整句话成了一个词元，中文没有被切分"
    # 相邻二字生成二元组：15 个字 → 14 个词元
    assert len(tokens) == len("三文鱼那次断供供应商赔了多少钱") - 1


def test_chinese_tokens_are_bigrams():
    assert tokenize("牛肉poke")[:1] == ["牛肉"]
    assert tokenize("退款政策") == ["退款", "款政", "政策"]


def test_single_chinese_char_stays_one_token():
    assert tokenize("月") == ["月"]


def test_no_long_chinese_run_survives():
    """任何词元里都不该出现 3 个以上连续汉字——出现就说明没切干净。"""
    text = "店长普遍反映停售那一周替代品的接受度比预想好，但客诉集中在为什么不提前说"
    for token in tokenize(text):
        assert longest_cjk_run(token) <= 2, "词元 %r 里有 %d 个连续汉字" % (token, longest_cjk_run(token))


# -- 英文和数字要留成整词 --------------------------------------------------------


def test_latin_words_stay_whole():
    """英文邮件（KB-022）靠整词匹配，不能被拆成字母二元组。"""
    tokens = tokenize("Salmon delivery of 2026-07-04")
    assert "salmon" in tokens
    assert "delivery" in tokens
    assert not any(token in ("salm", "almo", "eliv") for token in tokens)


def test_mixed_script_splits_at_the_boundary():
    tokens = tokenize("S02 的牛肉poke卖了多少")
    assert "s02" in tokens
    assert "牛肉" in tokens
    assert "poke" in tokens
    assert all(longest_cjk_run(token) <= 2 for token in tokens)


def test_normalise_full_width_and_case():
    """全角转半角、统一小写，比较与分词都走这一层。"""
    assert normalise("Ｓ０２") == "s02"
    assert normalise("Ｐｏｋｅ") == "poke"
    assert normalise("ＡＢＣ") == "abc"


# -- 虚词过滤按二字词元设计 ------------------------------------------------------


def test_stopword_pairs_are_dropped_from_content_tokens():
    """`STOP_CHARS` 里的「什么」「怎样」这类成对虚词，在词元是二字时才拦得住。"""
    terms = content_tokens("这个东西是什么")
    assert "什么" not in terms
    # 实词要留下
    assert "东西" in terms or "个东" in terms or "西是" in terms


# -- 真正要守的那条：查询词元必须能在索引里命中 ----------------------------------


@pytest.fixture(scope="module")
def index():
    settings = load_settings()
    return load_index(settings.kb_dir, settings.index_path, rebuild=False)


@pytest.mark.parametrize(
    "query",
    [
        "三文鱼那次断供供应商赔了多少钱",
        "发票怎么开",
        "台风那天几点提前闭店",
        "员工折扣几折，能不能和活动叠加",
        "外卖订单多久内可以退款",
        "冷萃乌龙茶首月的目标销量是多少",
        "S04 为什么不卖吞拿鱼三明治了",
    ],
)
def test_query_terms_hit_the_index(index, query):
    """每一条真实问句都要能在索引里命中至少一个片段。

    按空白切词时这里全部为 0——这正是 `/api/retrieve` 对不同问题返回同一组文档的原因。
    """
    weights = {token: 1.0 for token in tokenize(query)}
    scores = index.score_terms(weights, set(range(len(index.chunks))))
    assert scores, "查询词元在索引里一个都没命中：%s" % tokenize(query)


def test_index_terms_are_short_enough_to_match(index):
    """索引里的词元长度要和分词粒度一致，不能出现整句长度的词元。"""
    sizes = sorted(len(term) for term in index.postings)
    assert sizes[-1] <= 24, "索引里有超长词元，最长 %d 个字符" % sizes[-1]
    overlong = [term for term in index.postings if longest_cjk_run(term) > 2]
    assert overlong == [], "索引里有没切开的中文词元，例如 %r" % overlong[:3]


def test_query_and_document_share_tokens(index):
    """查询里的词元要真的出现在文档片段里（不是只出现在索引的键上）。"""
    from kbqa.index import BM25Index

    query_tokens = set(tokenize("外卖订单多久内可以退款"))
    chunk_tokens: set[str] = set()
    for position in range(len(index.chunks)):
        chunk_tokens.update(BM25Index._tokens_of(index, index.chunks[position]))
    assert query_tokens & chunk_tokens, "查询与文档没有任何共同词元"
