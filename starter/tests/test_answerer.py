"""回答层测试。

守两件事：

1. **引用要给最强的那条证据**。`_doc_block` 的候选排序曾经是升序，而它是照着顺序
   取前几条的，于是从最弱的句子开始挑——检索明明把 KB-011 排第一，答案却引用了
   一份周报和另一份退款政策。
2. **文档题的回答是挑出来的那几句，不是整篇原文**。契约 §5 对 `answer` 有 1200 字
   与 20 个不同数字的上限，倒一篇文档必然超限；而且倒的是检索第一名那篇、引用却是
   另一批文档，正文与引用自相矛盾。
"""

from __future__ import annotations

import re

import pytest

from kbqa.service import Service


@pytest.fixture(scope="module")
def service():
    return Service()


def test_doc_answer_cites_the_strongest_evidence(service):
    """引用要按证据分数从高到低给，不是从低到高。

    这道题的检索第一名是 KB-011，其中「单笔充值满 500 元，赠送 60 元」加权分 1.54，
    远高于被误引的 KB-051 周报（0.02）与 KB-013 退款政策（0.09）。
    """
    answer = service.chat("s-evidence", "会员现在单笔充值满 500 送多少？")
    cited = [citation["doc_id"] for citation in answer["citations"]]
    assert cited, "应当给出引用"
    assert cited[0] == "KB-011", "第一位引用应当是 KB-011，实际是 %s" % cited
    assert "60" in answer["answer"], "回答里要写出赠送金额：%r" % answer["answer"][:120]


def test_doc_answer_is_not_the_whole_document(service):
    """文档题的回答是挑出来的句子，不能是整篇原文。

    这道题的检索第一名是 KB-060《顾客反馈汇总》，整篇一千六百多字。原来会把它的全部
    片段倒进 `answer`，于是 1701 字、24 个数字，同时越过契约 §5 的两条上限
    （1200 字、20 个不同数字），正文来源还与引用对不上。
    """
    question = "7 月顾客投诉最集中的是什么问题？有多少条？"
    answer = service.chat("s-not-dumped", question)
    assert len(answer["answer"]) <= 1200, "回答 %d 字，超过契约 §5 的 1200 字上限" % len(
        answer["answer"]
    )
    numbers = {number.lstrip("0") or "0" for number in re.findall(r"\d+", answer["answer"])}
    assert len(numbers) <= 20, "回答里出现了 %d 个不同的数字，超过上限" % len(numbers)


def test_answer_is_much_shorter_than_the_document_it_cites(service):
    """更本质的一条：正文长度要远小于它引用那篇文档的全文字数。

    直接比长度，不依赖「多少字算超限」这个阈值——只要还在倒原文，这条必然红。
    """
    question = "7 月顾客投诉最集中的是什么问题？有多少条？"
    answer = service.chat("s-not-dumped-2", question)
    plan = service.planner.plan(question)
    result = service.retriever.search(
        plan.search_query, top_k=1, as_of=plan.as_of, store_id=plan.store_id
    )
    assert result.hits, "这道题应当有检索结果"
    doc_id = result.hits[0].doc_id
    full_text = "".join(chunk.text for chunk in service.retriever.index.chunks_of(doc_id))
    # 上限 200 字的资料 + 说明文字，远不到全文的一半
    assert len(answer["answer"]) < 0.5 * len(full_text), (
        "回答 %d 字，而 %s 全文 %d 字——像是把整篇文档倒出来了"
        % (len(answer["answer"]), doc_id, len(full_text))
    )


def test_doc_answer_and_citations_come_from_the_same_documents(service):
    """正文里提到的文档编号，必须都在 citations 里——两条路不能各走各的。"""
    for session, question in (
        ("s-同源-1", "会员现在单笔充值满 500 送多少？"),
        ("s-同源-2", "员工迟到多久算一次？"),
        ("s-同源-3", "顾客要开发票，怎么跟他说？"),
    ):
        answer = service.chat(session, question)
        cited = {citation["doc_id"] for citation in answer["citations"]}
        mentioned = set(re.findall(r"KB-\d+", answer["answer"]))
        assert mentioned <= cited, "%s\n  正文提到但没引用：%s" % (question, mentioned - cited)


def test_answer_stays_within_the_contract_limits(service):
    """契约 §5 的两条硬上限，逐题查一遍。"""
    for index, question in enumerate(
        [
            "外卖订单多久内可以申请退款？",
            "有顾客问牛肉poke 里有哪些过敏原，怎么答？",
            "Super Souper 现在周五晚上营业到几点？",
            "顾客要开发票，怎么跟他说？",
            "储值充值现在的赠送规则是什么？",
        ]
    ):
        answer = service.chat("s-limits-%d" % index, question)
        assert len(answer["answer"]) <= 1200, "%s：%d 字" % (question, len(answer["answer"]))
        numbers = {n.lstrip("0") or "0" for n in re.findall(r"\d+", answer["answer"])}
        assert len(numbers) <= 20, "%s：%d 个数字" % (question, len(numbers))
