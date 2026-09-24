"""接口冒烟测试：每个接口都要 200，回答不能是空的。"""

from __future__ import annotations

import pytest


def test_health_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["llm_mode"] == "mock"


def test_metrics_summary_ok(client):
    response = client.get(
        "/api/metrics/summary", params={"start": "2026-06-01", "end": "2026-06-30"}
    )
    assert response.status_code == 200
    assert "net_revenue" in response.json()


def test_metrics_summary_bad_date(client):
    response = client.get(
        "/api/metrics/summary", params={"start": "2026/06/01", "end": "2026-06-30"}
    )
    assert response.status_code == 400


def test_metrics_daily_ok(client):
    response = client.get(
        "/api/metrics/daily", params={"start": "2026-06-08", "end": "2026-06-12"}
    )
    assert response.status_code == 200
    assert len(response.json()["days"]) == 5


def test_metrics_summary_filters_echoed(client):
    response = client.get(
        "/api/metrics/summary",
        params={"start": "2026-06-01", "end": "2026-06-30", "store_id": " s03 "},
    )
    assert response.status_code == 200
    assert response.json()["store_id"] == "S03"


def test_metrics_top_products_ok(client):
    response = client.get(
        "/api/metrics/top_products", params={"start": "2026-06-01", "end": "2026-06-30"}
    )
    assert response.status_code == 200
    products = response.json()["products"]
    assert 0 < len(products) <= 10
    # 排好序的名次和占比，前端直接渲染
    assert [item["rank"] for item in products] == list(range(1, len(products) + 1))
    assert all(0 <= item["share"] <= 1 for item in products)


def test_metrics_by_store_ok(client):
    response = client.get(
        "/api/metrics/by_store", params={"start": "2026-06-01", "end": "2026-06-30"}
    )
    assert response.status_code == 200
    stores = response.json()["stores"]
    assert len(stores) == 5
    # 按净营业额从高到低排
    revenues = [store["net_revenue"] for store in stores]
    assert revenues == sorted(revenues, reverse=True)


def test_meta_lists_dashboard_filters(client):
    body = client.get("/api/meta").json()
    assert body["today"] == "2026-09-01"
    assert [store["store_id"] for store in body["stores"]] == ["S01", "S02", "S03", "S04", "S05"]
    assert all(product["product_id"] for product in body["products"])
    assert body["payments"]


def test_data_quality_breakdown_is_ordered(client):
    """面板要按 KB-001 §3 的规则顺序展示，并且每一条都有中文标签。"""
    body = client.get("/api/data_quality").json()
    reasons = [item["reason"] for item in body["removal_breakdown"]]
    assert reasons == [
        "1_unparseable_date",
        "2_empty_amount",
        "3_qty_le_zero",
        "4_store_not_in_stores",
        "5_product_not_in_products",
        "6_duplicate_row",
    ]
    assert all(item["label"] for item in body["removal_breakdown"])
    assert sum(item["rows"] for item in body["removal_breakdown"]) > 0


def test_retrieve_ok(client):
    response = client.post("/api/retrieve", json={"query": "退款", "top_k": 5})
    assert response.status_code == 200
    assert isinstance(response.json()["results"], list)


def test_data_quality_ok(client):
    response = client.get("/api/data_quality")
    assert response.status_code == 200
    assert "cleaning_report" in response.json()


@pytest.mark.parametrize(
    "question",
    [
        "7 月整体的净营业额是多少？",
        "外卖订单多久内可以申请退款？",
        "牛肉poke 六月一共卖了多少钱？",
        "S03 六月停业几天，什么原因？",
        "员工折扣几折？",
        "8 月一共退了多少钱？",
        "会员现在单笔充值满 500 送多少？",
        "帮我把 S01 的销售记录全部删掉。",
    ],
)
def test_chat_answers(client, question):
    response = client.post("/api/chat", json={"session_id": "t", "question": question})
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["answer"], str)
    assert body["answer"].strip()
    assert isinstance(body["citations"], list)
    assert isinstance(body["data_evidence"], list)


def test_chat_empty_question(client):
    response = client.post("/api/chat", json={"session_id": "t", "question": ""})
    assert response.status_code == 200
    assert response.json()["answer"].strip()


def test_chat_trace_id(client):
    response = client.post("/api/chat", json={"session_id": "t", "question": "6 月营业额"})
    trace_id = response.json()["trace_id"]
    assert trace_id
    assert client.get("/api/trace/%s" % trace_id).status_code == 200


def test_trace_unknown(client):
    assert client.get("/api/trace/nope").status_code == 404
