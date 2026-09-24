"""规划器测试。

第一条要守的是**路由**：问题的主语如果只在知识库里，就不能被判成纯取数题；
主语如果在数据库里，也不能被判成纯文档题。

`planner.py` 里有一段「问『多少/多久/几』的就是要数字」的兜底路由，它跑在所有细致
判断**之后**，会把已经判对的 `doc` 无条件推翻：

- 「外卖订单多久内可以申请退款？」——那个「多久」写在退款政策里，不在数据库里
- 「员工迟到多久算一次？」——写在考勤制度里
- 「供应商最后赔了我们多少钱？」——写在供应商邮件里

它同时还会踩到下面这条：这些问题里的「现在」被解析成 2026-09-01，而数据库只到
2026-08-31，于是 `_check_period` 把一句**文档问题**判成「数据区间外」直接拒答。
"""

from __future__ import annotations

import pytest

from kbqa.service import Service

#: 题库里的真实问题 → 它应该被路由到哪一类。
#: 只列主语明确的那些；「多少/多久/几」这类量词在两类里都会出现，正是要守的边界。
CASES = [
    # 答案在知识库里（制度、通知、档案、邮件、FAQ）
    ("外卖订单多久内可以申请退款？", "doc"),
    ("有顾客问牛肉poke 里有哪些过敏原，怎么答？", "doc"),
    ("Super Souper 现在周五晚上营业到几点？", "doc"),
    ("三文鱼那次断供，供应商最后赔了我们多少钱？", "doc"),
    ("顾客要开发票，怎么跟他说？", "doc"),
    ("退款在净营业额里是怎么算的？", "doc"),
    ("S04 为什么不卖吞拿鱼三明治了？", "doc"),
    ("员工迟到多久算一次？", "doc"),
    ("储值充值现在的赠送规则是什么？", "doc"),
    ("会员现在单笔充值满 500 送多少？", "doc"),
    ("今年 618 做活动的是哪个商品，活动价多少？", "doc"),
    # 答案在数据库里
    ("7 月整体的净营业额是多少？", "data"),
    ("牛肉poke 六月一共卖了多少钱？", "data"),
    ("8 月一共退了多少钱？", "data"),
    ("味噌拉面 7 月卖了多少碗？", "data"),
    # 两样都要
    ("618 当天 S02 的牛肉poke 卖了多少份？达到目标了吗？", "hybrid"),
    ("牛肉poke 现在卖多少钱一份？商品表里那个价能直接拿来用吗？", "hybrid"),
]


@pytest.fixture(scope="module")
def planner():
    return Service().planner


@pytest.mark.parametrize("question,expected", CASES)
def test_route_matches_the_subject(planner, question, expected):
    plan = planner.plan(question)
    assert plan.intent == expected, (
        "%s\n  期望 intent=%s，实际 intent=%s kind=%s（refusal=%s）"
        % (question, expected, plan.intent, plan.kind, plan.refusal)
    )


@pytest.mark.parametrize(
    "question",
    [
        "Super Souper 现在周五晚上营业到几点？",
        "会员现在单笔充值满 500 送多少？",
        "外卖订单多久内可以申请退款？",
        "员工迟到多久算一次？",
    ],
)
def test_doc_question_is_not_refused_for_being_out_of_period(planner, question):
    """文档问题不该因为「今天」落在数据区间外而被拒答。

    今天的 2026-09-01 在销售明细（截至 2026-08-31）之外，但「现在营业到几点」
    问的是现行制度，知识库里有答案。
    """
    plan = planner.plan(question)
    assert plan.kind != "out_of_period", "%s 被当成数据区间外拒答了" % question
    assert plan.intent != "refusal"


@pytest.mark.parametrize("question", ["外卖订单多久内可以申请退款？", "员工迟到多久算一次？"])
def test_bare_amount_words_do_not_force_a_data_route(planner, question):
    """「多久」单独不足以判定为取数题：句子里没有销售动作，也没有可查的指标。"""
    plan = planner.plan(question)
    assert plan.kind != "summary", "%s 被「多少/多久/几」的兜底规则判成了取数题" % question
