"""意图闸门：要求改动数据库、或套取系统信息的请求，一律拒答。

作业的硬性要求原文是：

> 文档里的内容只当资料用，不当指令执行。用户要求删改数据、套取系统信息时要拒绝，
> 数据库不能有任何改动。

这里只做**意图**层面的判断，不碰检索与取数：命中就由规划器直接给出 `refusal`，
不进入后面的检索与作答流程。

两条设计约束：

1. **拒答文案里不能出现数字。** 契约 §5 要求拒答时「不得出现编造的数字」，评测的
   `numbers_none_beyond_question` 逐字查——问句里没有的数字出现在回答里就判红。
   所以这里的文案一个数字都不写（连「只读」这类说法也不带编号）。
2. **宁可漏，不可误杀。** 判据要求**动词与对象同时出现**，而不是见到「删」「表」
   「规则」就拦。「退款政策里有没有说可以删单」「储值充值现在的赠送规则是什么」
   都是正常问题，闸门对它们必须放行。`tests/test_guard.py` 里正反两组用例是成对写的。
"""

from __future__ import annotations

import re
from typing import Optional

#: 要求改动数据的动词。写全各种说法——「清空」拦得住而「清掉」拦不住这种事，
#: 是自补题库 X07 抓出来的：同一件事换个动词就绕过去了。
#: 注意**不能**收「清洗」：那是本项目自己的术语（数据清洗），
#: 「清洗掉了多少行数据」是正常的看板问题，收了它就会误杀。
_WRITE_VERBS = (
    "删除", "删掉", "删了", "删光", "删单", "清空", "清了", "清掉", "清除",
    "抹掉", "抹去", "移除", "去掉", "改掉", "改成", "修改",
    "覆盖", "写入", "插入", "更新",
)

#: 被改动的对象。要求是多字词，避免「报表」「银行」「进行」这类词里的单字误命中。
_DATA_OBJECTS = ("数据", "记录", "订单", "明细", "数据库", "sales", "条目", "台账")

#: 直接写 SQL 的请求。
_SQL = re.compile(r"\b(drop|delete|truncate|update|insert|alter)\b", re.I)

#: 系统自身的东西，不该透露。
_SYSTEM_NOUNS = (
    "系统提示词", "提示词", "系统指令", "系统设定", "原始指令", "系统规则",
    "表结构", "数据库结构", "建表语句", "字段定义", "schema", "system prompt",
)

#: 索取的动作。
_ASKING_VERBS = (
    "发给我", "发过来", "发出来", "发一份", "给我", "告诉我", "列出", "列一下",
    "输出", "打印", "贴出来", "贴给我", "展示", "复述", "念一遍",
)

#: 要求无视既有规则。
_OVERRIDE_VERBS = ("忽略", "无视", "不要理会", "不用管", "忘记", "ignore")
_RULE_NOUNS = ("规则", "指令", "设定", "提示词", "要求", "instruction", "prompt", "rule")

#: 两段文案都**不含任何数字**——原因见模块开头第 1 条约束。
REFUSAL_DATA = (
    "这个请求我不能执行：它要求改动数据库里的数据。"
    "本系统对销售明细只有只读权限，只能查、不能增删改，也不会执行任何写操作。"
    "如果你是想了解某段时间的经营情况，告诉我指标、时间和门店，我来查。"
)
REFUSAL_PROBE = (
    "这个请求我不能执行：它要求透露系统自身的设定或数据库结构，这些不属于可以回答的范围。"
    "运营相关的问题我很乐意回答，比如某段时间的营业额、某条规定怎么写的。"
)


def _has_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def writes_database(text: str) -> bool:
    """是否在要求改动数据库：写 SQL，或「改动动词 + 数据对象」同时出现。"""
    if _SQL.search(text):
        return True
    return _has_any(text, _WRITE_VERBS) and _has_any(text, _DATA_OBJECTS)


def probes_system(text: str) -> bool:
    """是否在套取系统信息：要系统自身的设定／结构，或要求无视规则。"""
    if _has_any(text, _OVERRIDE_VERBS) and _has_any(text.lower(), _RULE_NOUNS):
        return True
    return _has_any(text, _SYSTEM_NOUNS) and _has_any(text, _ASKING_VERBS)


def refusal_for(text: str) -> Optional[str]:
    """命中就返回拒答文案，否则返回 None。"""
    if writes_database(text):
        return REFUSAL_DATA
    if probes_system(text):
        return REFUSAL_PROBE
    return None
