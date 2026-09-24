"""分词。

中文不写空格，所以「按空白切词」等于不切词：一句话变成一个词元，查询词元在索引里
一个都命不中，BM25 对任何问题都返回 0 分。这里改成按字符类型分段的混合分词：

- 汉字走**重叠的字符二元组**（`退款政策` → `退款`/`款政`/`政策`）；
- 字母、数字以及夹在其中的 `- _ . / :` 整段保留（`2026-07-04`、`kb-022`、`s02`）。

选二元组而不是分词词典，是因为它不需要词典就能覆盖任意新词——评审会把
`knowledge_base/` 整份换掉、文档有增有改，二元组照样能切，不会因为词典没收录而漏词。
代价是同义改写（文档写“退款”、用户问“退钱”）仍然靠别名词典兜底，这一点记在 README 的已知限制里。
"""

from __future__ import annotations

import re
import unicodedata

#: 分词规则变了，索引缓存必须失效。
TOKENIZER_VERSION = "tokenizer-3"

#: 中日韩表意文字（含扩展 A U+3400-U+4DBF）、统一表意文字（U+4E00-U+9FFF）、
#: 兼容表意文字（U+F900-U+FAFF）、日文假名（U+3040-U+30FF）。
_CJK_RANGES = "\\u3400-\\u4dbf\\u4e00-\\u9fff\\uf900-\\ufaff\\u3040-\\u30ff"

#: 汉字串 或 字母数字串（允许中间夹 `- _ . / :`，好让日期与编号保持完整）。
_RUN = re.compile("[%s]+|[0-9a-z]+(?:[-_./:][0-9a-z]+)*" % _CJK_RANGES)
_IS_CJK = re.compile("[%s]" % _CJK_RANGES)

#: 中文里几乎不携带信息的字。只用在“查询覆盖率”上，索引照常保留全部词。
STOP_CHARS = frozenset("的了吗呢是在有和与及或就都也还把被给对从向于个些这那哪什么怎样如何多少几请帮我你他它可以能要想会一下少吧啊呀们么样过得着为所")
STOP_WORDS = frozenset("the a an of to in is are and or for on at it this that how what".split())


def normalise(text: str) -> str:
    """全角转半角、统一大小写，比较与分词都走这一层。"""
    return unicodedata.normalize("NFKC", text or "").lower()


def bigrams(text: str) -> list[str]:
    """重叠的字符二元组。一到两个字的串原样返回。"""
    if len(text) <= 2:
        return [text]
    return [text[index : index + 2] for index in range(len(text) - 1)]


def tokenize(text: str) -> list[str]:
    """中英混排分词：汉字按二元组切开，字母数字整段保留。"""
    tokens: list[str] = []
    for run in _RUN.finditer(normalise(text)):
        piece = run.group(0)
        if _IS_CJK.match(piece[0]):
            tokens.extend(bigrams(piece))
        else:
            tokens.append(piece)
    return tokens


def content_tokens(text: str) -> list[str]:
    """去掉虚词之后的查询词，用来算“这个问题被文档覆盖了多少”。"""
    kept = []
    for token in tokenize(text):
        if token in STOP_WORDS:
            continue
        if all(char in STOP_CHARS for char in token):
            continue
        kept.append(token)
    return kept
