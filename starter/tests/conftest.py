"""测试夹具。

检索这块在测试里整个换成固定返回，这样测试就不用跟着知识库一起改，
跑起来也快。要看真实检索效果直接起服务问两句就行。

**注意这个替身的范围。** 原来是把 `Retriever.search` 打在**类**上、且从不还原，
于是它会在整个 session 里生效：后面任何针对真实检索器的测试拿到的都是这里这份固定返回。
更麻烦的是，正因为检索被换掉了，交接文档里「测试全部通过」并不能说明检索是对的——
检索相关的缺陷一个都漏不掉。所以现在只替换 API 用的那个 `Service` 实例。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FAKE_TEXT = "退款政策 v2 > 三、时限：外卖订单在订单送达后 24 小时内可以申请退款。"


@pytest.fixture(scope="session")
def client(tmp_path_factory):
    os.environ["VAR_DIR"] = str(tmp_path_factory.mktemp("var"))
    for key in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        os.environ.pop(key, None)

    from fastapi.testclient import TestClient

    from kbqa import retriever as retriever_module
    from kbqa import server

    # 挂成实例属性，所以不需要 self：调用时只有 (query, top_k)。
    def fake_search(query, top_k=5, **kwargs):
        hit = retriever_module.Hit(
            doc_id="KB-013",
            chunk_id="KB-013#1",
            score=42.0,
            text=FAKE_TEXT,
            source_text=FAKE_TEXT,
            meta={"title": "退款政策 v2", "status": "现行"},
        )
        return retriever_module.SearchResult(
            hits=[hit][:top_k],
            query=query,
            terms=[],
            expansions=[],
            filtered=[],
            coverage=1.0,
        )

    # 只替换这个 Service 实例上的检索：实例属性遮蔽类方法，别的 Retriever 实例
    # （真实检索器的测试）完全不受影响。
    server.service().retriever.search = fake_search
    return TestClient(server.app)
