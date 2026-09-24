"""会话与追问测试。

契约 §5：同一个 `session_id` 的多次请求视为同一段对话，要支持追问。
`/api/chat` 里 `history` 从会话存储里取出来了，却**没有传给规划器**：

    history = self.sessions.history(session_id)
    plan = self.planner.plan(question)          # ← 少了 history

于是规划器里的 `followups.resolve(question, history or [])` 永远拿到空列表，
每一句追问都被当成「没有上文的孤立提问」——短句直接回一句“请把问题补完整”，
长句则按字面重新规划，指代全部丢失。
"""

from __future__ import annotations

import pytest

from kbqa.service import Service
from kbqa.sessions import SessionStore


def test_store_keeps_sessions_apart():
    """会话存储必须按 session_id 分开存。

    原来的实现是一条平铺列表：`history()` 不管传什么 session_id 都返回同一条，
    `append()` 也不看 session_id。契约 §5 要求「不同 session_id 之间不能串线」。
    """
    store = SessionStore()
    store.append("会话甲", {"question": "甲的问题"})
    store.append("会话乙", {"question": "乙的问题"})
    assert [turn["question"] for turn in store.history("会话甲")] == ["甲的问题"]
    assert [turn["question"] for turn in store.history("会话乙")] == ["乙的问题"]
    assert store.history("没见过的会话") == []


def test_store_turn_limit_is_per_session():
    """「最近几轮」是每个会话各自的窗口，不能被别的会话挤掉。"""
    store = SessionStore(max_turns=2)
    for index in range(4):
        store.append("甲", {"question": "甲%d" % index})
    store.append("乙", {"question": "乙0"})
    assert [turn["question"] for turn in store.history("甲")] == ["甲2", "甲3"]
    assert [turn["question"] for turn in store.history("乙")] == ["乙0"]


def test_store_caps_the_number_of_sessions():
    """会话数有上限：超了先淘汰最久没用过的那个，免得内存无限涨。"""
    store = SessionStore(max_sessions=2, max_turns=4)
    store.append("甲", {"question": "甲"})
    store.append("乙", {"question": "乙"})
    store.append("丙", {"question": "丙"})
    assert store.history("甲") == [], "最久未用的会话没有被淘汰"
    assert store.history("乙"), "最近用过的会话不该被淘汰"
    assert store.history("丙")


def test_store_without_session_id_has_no_history():
    """没给 session_id 就没有「同一段对话」可言：不留历史，也不串到别人身上。"""
    store = SessionStore()
    store.append(None, {"question": "没带 session_id 的一轮"})
    store.append("", {"question": "空字符串"})
    assert store.history(None) == []
    assert store.history("") == []
    assert store.history("甲") == []


@pytest.fixture(scope="module")
def service():
    return Service()


def test_follow_up_keeps_the_topic(service):
    """「那 6 月的时候呢」要接着上一轮的话题走，不能当成孤立提问。"""
    first = service.chat("s-follow-1", "会员单笔充值满 500 送多少？")
    assert first["answer_type"] != "clarify"
    second = service.chat("s-follow-1", "那 6 月的时候呢？")
    assert second["answer_type"] != "clarify", "追问被当成了没有上文的孤立提问"


def test_sessions_do_not_bleed_into_each_other(service):
    """契约 §5：不同 session_id 之间不能串线。"""
    service.chat("s-bleed-a", "会员单笔充值满 500 送多少？")
    other = service.chat("s-bleed-b", "那 6 月的时候呢？")
    assert other["answer_type"] == "clarify", "另一个会话里没有上文，应当反问"


def test_history_is_actually_recorded(service):
    """会话存储要记下每一轮，否则追问无从谈起。"""
    service.chat("s-history", "退款政策怎么规定的？")
    history = service.sessions.history("s-history")
    assert history, "会话历史是空的"
    assert history[-1]["question"] == "退款政策怎么规定的？"


def test_planner_receives_the_history(service):
    """直接盯住那一行：规划器要拿到历史，`standalone` 才会被补全。"""
    service.chat("s-planner", "味噌拉面 7 月卖了多少碗？")
    history = service.sessions.history("s-planner")
    plan = service.planner.plan("那 6 月呢？", history)
    assert plan.intent != "clarify", "带着上文时不该反问"
    assert plan.standalone != "那 6 月呢？", "追问没有被补成完整问题"
