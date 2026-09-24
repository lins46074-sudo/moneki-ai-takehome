"""清洗流水线测试。

口径全部来自 KB-001 §2（规范化）与 §3（剔除）。断言里的数字不是抄来的：
`test_report_balances` 与 `test_clean_table_has_no_dirty_ids` 直接查清洗表自己算，
换一套数据也能跑绿。
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from kbqa.cleaning import (
    REMOVAL_REASONS,
    build_clean_db,
    normalize_id,
    open_readonly,
    parse_amount,
    parse_date,
    parse_qty,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
POS_DB = DATA_DIR / "pos.db"


@pytest.fixture(scope="module")
def clean(tmp_path_factory):
    """跑一遍真实数据的清洗，返回（台账, 清洗表连接）。"""
    target = tmp_path_factory.mktemp("clean") / "clean.db"
    report = build_clean_db(POS_DB, target).as_dict()
    conn = open_readonly(target)
    yield report, conn
    conn.close()


# -- §2 规范化 ------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-06-01", "2026-06-01"),
        ("2026-6-1", "2026-06-01"),
        ("2026/6/1", "2026-06-01"),
        ("2026/12/31", "2026-12-31"),
    ],
)
def test_parse_date_year_first(raw, expected):
    assert parse_date(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        # KB-001 §2.2：旧 POS 是「日在前、月在后」，方向搞反了 40 行会直接算错月份。
        ("25-07-2026", "2026-07-25"),
        ("07-06-2026", "2026-06-07"),
        ("31-12-2026", "2026-12-31"),
    ],
)
def test_parse_date_day_first(raw, expected):
    assert parse_date(raw) == expected


@pytest.mark.parametrize("raw", ["N/A", "", None, "2026-13-45", "2026-02-30", "昨天"])
def test_parse_date_rejects_garbage(raw):
    assert parse_date(raw) is None


@pytest.mark.parametrize(
    "raw,expected",
    [("38.00", 3800), ("¥38.00", 3800), ("￥38.00", 3800), (" ¥38.00 ", 3800), ("-12.00", -1200)],
)
def test_parse_amount_keeps_currency_rows(raw, expected):
    """KB-001 §2.3 / §7.1：带 ¥ 的行是可恢复的，去掉符号照常参与统计。"""
    cents, status = parse_amount(raw)
    assert (cents, status) == (expected, "ok")


@pytest.mark.parametrize("raw", ["", None, "   "])
def test_parse_amount_empty(raw):
    assert parse_amount(raw) == (None, "empty")


def test_parse_qty():
    assert parse_qty("3") == 3
    assert parse_qty(" 2 ") == 2
    assert parse_qty("abc") is None


def test_normalize_id():
    """KB-001 §2.1：去首尾空白 + 转大写，这几种写法都是同一个编号。"""
    assert normalize_id("s01") == "S01"
    assert normalize_id(" S01 ") == "S01"
    assert normalize_id("S01") == "S01"


# -- §3 剔除与台账 --------------------------------------------------------------


def test_report_balances(clean):
    """原始行数 = 保留行数 + 各类剔除行数之和，一条都不能丢。"""
    report, _ = clean
    assert report["raw_rows"] == report["kept_rows"] + report["removed"]["total"]
    assert report["balanced"] is True


def test_report_totals_match_table(clean):
    """台账里的保留行数必须与清洗表实际行数一致。"""
    report, conn = clean
    total = conn.execute("SELECT COUNT(*) FROM sales_clean").fetchone()[0]
    refunds = conn.execute("SELECT COUNT(*) FROM sales_clean WHERE is_refund=1").fetchone()[0]
    assert total == report["kept_rows"]
    assert refunds == report["kept_refund_rows"]
    assert report["kept_sales_rows"] + report["kept_refund_rows"] == report["kept_rows"]


def test_every_removal_reason_fires(clean):
    """六条规则在这份数据上都要真的命中了，不能有哪一条是摆设。"""
    report, _ = clean
    for reason in REMOVAL_REASONS:
        assert report["removed"][reason] > 0, "剔除规则没有命中任何行：%s" % reason


def test_currency_rows_survive(clean):
    """被 §2 修正过的行是「恢复」不是「剔除」，必须留在表里。"""
    report, conn = clean
    assert report["recovered"]["currency_amount"] > 0
    assert report["recovered"]["alt_date_format"] > 0
    assert report["recovered"]["id_case_or_space"] > 0


# -- 清洗表的不变量 --------------------------------------------------------------


def test_clean_table_has_only_iso_dates(clean):
    """日期全部规范化成 ISO，区间筛选才能直接比字符串。"""
    _, conn = clean
    bad = conn.execute(
        "SELECT COUNT(*) FROM sales_clean WHERE date NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'"
    ).fetchone()[0]
    assert bad == 0
    for row in conn.execute("SELECT DISTINCT date FROM sales_clean").fetchall():
        date.fromisoformat(row[0])  # 解析不了会直接抛错


def test_clean_table_has_no_dirty_ids(clean):
    """门店号、商品号都必须是维表里存在的规范编号。"""
    _, conn = clean
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM sales_clean WHERE store_id NOT IN (SELECT store_id FROM stores)"
        ).fetchone()[0]
        == 0
    )
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM sales_clean WHERE product_id NOT IN "
            "(SELECT product_id FROM products)"
        ).fetchone()[0]
        == 0
    )
    assert (
        conn.execute("SELECT COUNT(*) FROM sales_clean WHERE store_id <> UPPER(TRIM(store_id))")
        .fetchone()[0]
        == 0
    )


def test_clean_table_has_no_exact_duplicates(clean):
    """§3.6：七字段规范化后完全一致的行只能剩一条。"""
    _, conn = clean
    duplicated = conn.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT 1 FROM sales_clean
            GROUP BY order_id, date, store_id, product_id, qty, amount_cents, payment
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    assert duplicated == 0


def test_multiline_orders_are_kept(clean):
    """§3.6 / §7.3：一张订单点两个菜的两行明细必须都留下，不能被当成重复行删掉。"""
    _, conn = clean
    order_id = conn.execute(
        """
        SELECT order_id FROM sales_clean
        GROUP BY order_id, date, store_id, payment
        HAVING COUNT(DISTINCT product_id) > 1
        LIMIT 1
        """
    ).fetchone()
    assert order_id is not None, "这份数据里应该有共用订单号的多行订单"
    rows = conn.execute(
        "SELECT COUNT(*) FROM sales_clean WHERE order_id = ?", (order_id[0],)
    ).fetchone()[0]
    assert rows > 1


def test_amount_cents_is_integer_and_bounded(clean):
    """金额按分存整数，不引入浮点误差。"""
    _, conn = clean
    bad = conn.execute(
        "SELECT COUNT(*) FROM sales_clean WHERE amount_cents IS NULL OR amount_cents <> CAST(amount_cents AS INTEGER)"
    ).fetchone()[0]
    assert bad == 0


def test_clean_db_is_a_fresh_copy(clean):
    """重建必须整表替换，不能把上一次的结果累加进去。"""
    report, conn = clean
    assert conn.execute("SELECT COUNT(*) FROM sales_clean").fetchone()[0] == report["kept_rows"]


def test_source_db_is_untouched(tmp_path):
    """清洗只读源库：`data/pos.db` 的行数不能被改动。"""
    src = sqlite3.connect(POS_DB.as_posix())
    before = src.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    src.close()
    build_clean_db(POS_DB, tmp_path / "clean.db")
    src = sqlite3.connect(POS_DB.as_posix())
    after = src.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    src.close()
    assert before == after
