"""指标口径测试，口径来自 KB-001 §4。

分两层：

- **小数据集**：自己造一份几十行的数据，每个数字都能手算，断言的是精确值。
  多行订单、退款、空日期、闭区间边界都在这里覆盖。
- **真实数据**：只断言不变量（汇总 = 各天之和、区间长度、筛选可加性），
  所以换一套 `data/` 也能跑绿。
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from kbqa.tools import DataTools

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
POS_DB = DATA_DIR / "pos.db"

#: 测试用的小表结构，与清洗表一致，但不依赖 kbqa.cleaning 的实现。
SCHEMA = """
CREATE TABLE stores (store_id TEXT PRIMARY KEY, store_name TEXT, category TEXT, district TEXT);
CREATE TABLE products (product_id TEXT PRIMARY KEY, product_name TEXT,
                       product_category TEXT, unit_price REAL);
CREATE TABLE sales_clean (
    order_id TEXT, date TEXT, store_id TEXT, product_id TEXT,
    qty INTEGER, amount_cents INTEGER, payment TEXT, is_refund INTEGER
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""

#: 手算样例：(order_id, date, store_id, product_id, qty, amount_cents, payment)
#:
#: 06-01 S01：ORD1 一张订单点了两个菜（P01 20.00 + P02 10.00），ORD2 又一单 30.00
#:            → 销售行 3 行、净额 60.00、有效订单 2 单、销量 6
#: 06-01 S02：ORD3 一单 50.00 → 当天合计净额 110.00、订单 3 单、销量 7
#: 06-02 S01：ORD4 销售 10.00，ORD5 退款 5.00 → 净额 5.00、退款 5.00、订单 1 单、销量 1−1=0
#: 06-03     ：没有任何行 → 全 0、客单价 null
#:
#: 注意退款行的 `qty` 记的是**正数**（退了几份），金额才是负数——与 `data/pos.db`
#: 里的约定一致，由 `test_refund_rows_have_positive_qty` 守着。
ROWS = [
    ("ORD1", "2026-06-01", "S01", "P01", 2, 2000, "现金"),
    ("ORD1", "2026-06-01", "S01", "P02", 1, 1000, "现金"),
    ("ORD2", "2026-06-01", "S01", "P01", 3, 3000, "微信"),
    ("ORD3", "2026-06-01", "S02", "P01", 1, 5000, "微信"),
    ("ORD4", "2026-06-02", "S01", "P01", 1, 1000, "现金"),
    ("ORD5", "2026-06-02", "S01", "P01", 1, -500, "现金"),
]


def make_tools(path: Path, rows) -> DataTools:
    conn = sqlite3.connect(path.as_posix())
    conn.executescript(SCHEMA)
    conn.executemany(
        "INSERT INTO stores VALUES (?,?,?,?)",
        [("S01", "甲店", "拉面", "徐汇"), ("S02", "乙店", "轻食", "静安")],
    )
    conn.executemany(
        "INSERT INTO products VALUES (?,?,?,?)",
        [("P01", "牛肉poke", "轻食", 30.0), ("P02", "三文鱼poke", "轻食", 12.0)],
    )
    conn.executemany(
        "INSERT INTO sales_clean VALUES (?,?,?,?,?,?,?,?)",
        [(o, d, s, p, q, a, pay, 1 if a < 0 else 0) for o, d, s, p, q, a, pay in rows],
    )
    conn.commit()
    conn.close()
    return DataTools(path)


@pytest.fixture
def sample(tmp_path):
    return make_tools(tmp_path / "sample.db", ROWS)


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    """真实数据的清洗表：重跑一次清洗，不依赖 var/ 里已有的产物。"""
    from kbqa.cleaning import build_clean_db

    target = tmp_path_factory.mktemp("metrics") / "clean.db"
    build_clean_db(POS_DB, target)
    tools = DataTools(target)
    period = tools.data_period()
    yield tools, period
    tools.close()


# -- 小数据集：精确值 ------------------------------------------------------------


def test_summary_hand_computed(sample):
    """区间 06-01..06-03：净额 115.00、退款 5.00、3+1=4 单、销量 7+0=7。"""
    got = sample.query_metrics("2026-06-01", "2026-06-03")
    assert got["net_revenue"] == 115.00
    assert got["refund_amount"] == 5.00
    assert got["orders"] == 4
    assert got["qty"] == 7
    # 11500 分 ÷ 100 ÷ 4 单 = 28.75
    assert got["aov"] == 28.75


def test_summary_end_is_inclusive(sample):
    """契约 §2 的区间是闭区间：只查 06-01 必须查到当天，不能少算一天。"""
    got = sample.query_metrics("2026-06-01", "2026-06-01")
    assert got["net_revenue"] == 110.00
    assert got["orders"] == 3
    assert got["qty"] == 7

    # 只查 06-02：销售 10.00 减退款 5.00
    day2 = sample.query_metrics("2026-06-02", "2026-06-02")
    assert day2["net_revenue"] == 5.00
    assert day2["refund_amount"] == 5.00
    assert day2["orders"] == 1
    assert day2["qty"] == 0


def test_refund_reduces_net_revenue(sample):
    """KB-001 §4 / §6：v3 起退款行计入净营业额，是相减不是忽略。

    只统计正向销售的实现会在这里给出 10.00，比正确值多 5.00。
    """
    got = sample.query_metrics("2026-06-02", "2026-06-02")
    assert got["net_revenue"] == 5.00

    # 退款单独占一天时，净额必须是负数，而不是 0
    refund_only = make_tools(sample.db_path.parent / "refund_only.db", [
        ("ORD9", "2026-06-05", "S01", "P01", 2, -800, "现金"),
    ])
    got = refund_only.query_metrics("2026-06-05", "2026-06-05")
    assert got["net_revenue"] == -8.00
    assert got["refund_amount"] == 8.00
    assert got["qty"] == -2


def test_orders_counts_distinct_order_id(sample):
    """KB-001 §4：多行订单算 1 单，退款行不单独计为订单。

    按明细行数算（`COUNT(*)`）的实现会给出 6 单。
    """
    got = sample.query_metrics("2026-06-01", "2026-06-01", store_id="S01")
    assert got["orders"] == 2
    assert got["qty"] == 6
    assert got["net_revenue"] == 60.00


def test_store_and_product_filters(sample):
    assert sample.query_metrics("2026-06-01", "2026-06-03", store_id="S02")["net_revenue"] == 50.00
    assert sample.query_metrics("2026-06-01", "2026-06-03", store_id="S01")["net_revenue"] == 65.00
    # P02 只在 ORD1 的第二行出现
    p02 = sample.query_metrics("2026-06-01", "2026-06-03", product_id="P02")
    assert p02["net_revenue"] == 10.00
    assert p02["qty"] == 1
    assert p02["orders"] == 1


def test_filter_echo_is_normalized(sample):
    """回显的筛选值用规范化后的大写编号，与真正查的一致。"""
    got = sample.query_metrics("2026-06-01", "2026-06-03", store_id=" s01 ", product_id="p01")
    assert got["store_id"] == "S01"
    assert got["product_id"] == "P01"
    assert sample.query_metrics("2026-06-01", "2026-06-03")["store_id"] is None


def test_empty_range_returns_zeros_not_error(sample):
    """契约 §2：区间内没有数据时数值字段返回 0、客单价返回 null，不报错。"""
    got = sample.query_metrics("2026-01-01", "2026-01-31")
    assert got["net_revenue"] == 0
    assert got["refund_amount"] == 0
    assert got["orders"] == 0
    assert got["qty"] == 0
    assert got["aov"] is None


def test_aov_rounds_half_up(sample):
    """KB-001 §4 说「四舍五入」，不是 Python 默认的银行家舍入。

    10.05 ÷ 2 = 5.025：四舍五入是 5.03，银行家舍入会给出 5.02。
    """
    tools = make_tools(sample.db_path.parent / "rounding.db", [
        ("ORD6", "2026-06-06", "S01", "P01", 1, 500, "现金"),
        ("ORD7", "2026-06-06", "S01", "P01", 1, 505, "现金"),
    ])
    assert tools.query_metrics("2026-06-06", "2026-06-06")["aov"] == 5.03


# -- 小数据集：按天 --------------------------------------------------------------


def test_daily_covers_every_day(sample):
    """契约 §3：每一天都要有一条，没营业额的日期补 0、客单价补 null。"""
    days = sample.daily_metrics("2026-06-01", "2026-06-04")["days"]
    assert [d["date"] for d in days] == [
        "2026-06-01",
        "2026-06-02",
        "2026-06-03",
        "2026-06-04",
    ]
    assert days[0]["net_revenue"] == 110.00
    assert days[1]["net_revenue"] == 5.00
    assert days[2] == {
        "date": "2026-06-03",
        "net_revenue": 0,
        "refund_amount": 0,
        "orders": 0,
        "aov": None,
        "qty": 0,
    }
    assert days[3]["net_revenue"] == 0


def test_daily_matches_summary(sample):
    """同区间的汇总必须等于各天之和，两个接口不能各算一套。"""
    summary = sample.query_metrics("2026-06-01", "2026-06-04")
    days = sample.daily_metrics("2026-06-01", "2026-06-04")["days"]
    assert round(sum(d["net_revenue"] for d in days), 2) == summary["net_revenue"]
    assert round(sum(d["refund_amount"] for d in days), 2) == summary["refund_amount"]
    assert sum(d["orders"] for d in days) == summary["orders"]
    assert sum(d["qty"] for d in days) == summary["qty"]


def test_daily_aov_matches_own_day(sample):
    for day in sample.daily_metrics("2026-06-01", "2026-06-04")["days"]:
        if day["orders"]:
            assert day["aov"] == round(day["net_revenue"] / day["orders"], 2)
        else:
            assert day["aov"] is None


def test_daily_respects_filters(sample):
    days = sample.daily_metrics("2026-06-01", "2026-06-02", store_id="S01")["days"]
    assert [d["net_revenue"] for d in days] == [60.00, 5.00]
    p02 = sample.daily_metrics("2026-06-01", "2026-06-02", product_id="P02")["days"]
    assert [d["net_revenue"] for d in p02] == [10.00, 0]


# -- 真实数据：不变量 ------------------------------------------------------------


def test_real_daily_matches_summary(real):
    tools, period = real
    start, end = period["start"], period["end"]
    summary = tools.query_metrics(start, end)
    days = tools.daily_metrics(start, end)["days"]
    assert round(sum(d["net_revenue"] for d in days), 2) == summary["net_revenue"]
    assert round(sum(d["refund_amount"] for d in days), 2) == summary["refund_amount"]
    assert sum(d["orders"] for d in days) == summary["orders"]
    assert sum(d["qty"] for d in days) == summary["qty"]


def test_real_daily_is_contiguous(real):
    tools, period = real
    days = tools.daily_metrics(period["start"], period["end"])["days"]
    assert len(days) == (date.fromisoformat(period["end"]) - date.fromisoformat(period["start"])).days + 1
    for earlier, later in zip(days, days[1:]):
        assert date.fromisoformat(later["date"]) - date.fromisoformat(earlier["date"]) == timedelta(days=1)


def test_real_single_day_equals_daily_row(real):
    """闭区间最容易错的地方：取任意一天单查，结果必须等于按天列表里的那一天。"""
    tools, period = real
    days = tools.daily_metrics(period["start"], period["end"])["days"]
    for probe in (days[0], days[len(days) // 2], days[-1]):
        assert tools.query_metrics(probe["date"], probe["date"]) == {
            "start": probe["date"],
            "end": probe["date"],
            "store_id": None,
            "product_id": None,
            "net_revenue": probe["net_revenue"],
            "refund_amount": probe["refund_amount"],
            "orders": probe["orders"],
            "aov": probe["aov"],
            "qty": probe["qty"],
        }


def test_real_store_totals_add_up(real):
    """门店拆分的和 = 总账，说明筛选维度没有漏算或重复。"""
    tools, period = real
    start, end = period["start"], period["end"]
    total = tools.query_metrics(start, end)
    per_store = tools.by_store(start, end)["stores"]
    assert len(per_store) == 5
    assert round(sum(s["net_revenue"] for s in per_store), 2) == total["net_revenue"]
    assert sum(s["orders"] for s in per_store) == total["orders"]
    assert sum(s["qty"] for s in per_store) == total["qty"]
    assert round(sum(s["refund_amount"] for s in per_store), 2) == total["refund_amount"]


def test_real_every_store_is_in_the_stores_table(real):
    tools, _ = real
    known = {row["store_id"] for row in tools.stores()}
    for row in tools.conn.execute("SELECT DISTINCT store_id FROM sales_clean"):
        assert row[0] in known


def test_real_data_period_is_iso(real):
    _, period = real
    assert date.fromisoformat(period["start"]) < date.fromisoformat(period["end"])


def test_refund_rows_have_positive_qty(real):
    """守住数据约定：退款行的 `qty` 是**正数**（退了几份），金额才是负数。

    KB-001 §4 的销量是「销售行 qty 之和 − 退款行 qty 之和」，这句只有在退款行
    qty 为正时才等于「卖出去减退回来」。哪天数据换成用负数记退款数量，这条会先红，
    而不是让销量悄悄算反。
    """
    tools, _ = real
    negative = tools.conn.execute(
        "SELECT COUNT(*) FROM sales_clean WHERE amount_cents < 0 AND qty < 0"
    ).fetchone()[0]
    assert negative == 0
    assert tools.conn.execute("SELECT COUNT(*) FROM sales_clean WHERE amount_cents < 0").fetchone()[0] > 0


def test_real_no_negative_orders(real):
    tools, period = real
    for day in tools.daily_metrics(period["start"], period["end"])["days"]:
        assert day["orders"] >= 0
        assert (day["aov"] is None) == (day["orders"] == 0)
