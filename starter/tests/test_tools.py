"""取数工具的只读性测试。

作业的硬性要求：「用户要求删改数据、套取系统信息时要拒绝，数据库不能有任何改动。」

三处都要守：

1. `DataTools` 的连接**本身**就是只读的——`open_readonly()` 以前只是名字叫只读，
   实际开的是普通读写连接，`run_sql` 还会主动 `commit()`；
2. `run_sql` 拒绝任何不是 `SELECT` / `WITH` 开头的语句，这是第二道闸；
3. 模型能走的那条路（`Service.run_tool("run_sql", ...)`）同样拦得住——
   工具是暴露给模型的，一条提示注入就能到那里。
"""

from __future__ import annotations

import shutil
import sqlite3

import pytest

from kbqa.cleaning import build_clean_db
from kbqa.config import load_settings
from kbqa.tools import DataTools


@pytest.fixture(scope="module")
def clean_db(tmp_path_factory):
    settings = load_settings()
    target = tmp_path_factory.mktemp("readonly") / "clean.db"
    build_clean_db(settings.source_db, target)
    return target


@pytest.fixture
def tools(clean_db, tmp_path):
    """每个测试拿一份**独立副本**。

    修好之前这些破坏性操作是真能跑通的，共享一份连接会让「DROP TABLE」把后面
    测试的数据一起搞坏，红的就不止该红的那几条了——那样的红证据不干净。
    """
    target = tmp_path / "clean.db"
    shutil.copyfile(clean_db, target)
    instance = DataTools(target)
    yield instance
    instance.close()


def test_connection_itself_refuses_writes(tools):
    """连接就是只读的：连 UPDATE 都执行不了，不靠上层拦。"""
    with pytest.raises(sqlite3.OperationalError):
        tools.conn.execute("UPDATE sales_clean SET qty = 0")


def test_connection_refuses_drop(tools):
    with pytest.raises(sqlite3.OperationalError):
        tools.conn.execute("DROP TABLE sales_clean")


def test_reads_still_work(tools):
    """只读不等于不能查：正常的取数要照常。"""
    assert tools.valid_sales_rows() > 0
    assert tools.query_metrics("2026-06-01", "2026-06-30")["orders"] > 0


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE sales_clean SET qty = 0",
        "DELETE FROM sales_clean",
        "DROP TABLE sales_clean",
        "INSERT INTO sales_clean VALUES ('x','2026-06-01','S01','P01',1,1,'现金',0)",
        "ALTER TABLE sales_clean ADD COLUMN hack TEXT",
        "  update sales_clean set qty = 0  ",
    ],
)
def test_run_sql_refuses_writes(tools, sql):
    """`run_sql` 只接受只读查询，别的语句一律拒绝并说明原因。"""
    result = tools.run_sql(sql)
    assert "error" in result, "写操作没有被拒绝：%r" % sql
    assert not result.get("rows")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT COUNT(*) AS n FROM sales_clean",
        "select count(*) as n from sales_clean",
        "WITH t AS (SELECT 1 AS n) SELECT n FROM t",
        "SELECT date, SUM(amount_cents) FROM sales_clean GROUP BY date LIMIT 3",
    ],
)
def test_run_sql_allows_read_only_queries(tools, sql):
    result = tools.run_sql(sql)
    assert "error" not in result, "只读查询被误拦：%r -> %s" % (sql, result)
    assert result["rows"], "只读查询应当返回数据"


def test_data_survives_write_attempts(tools):
    """被拒绝之后，数据必须一个字节都没变。"""
    before = tools.valid_sales_rows()
    quantity = tools.conn.execute("SELECT SUM(qty) FROM sales_clean").fetchone()[0]
    for sql in ("UPDATE sales_clean SET qty = 0", "DELETE FROM sales_clean", "DROP TABLE sales_clean"):
        tools.run_sql(sql)
    assert tools.valid_sales_rows() == before
    assert tools.conn.execute("SELECT SUM(qty) FROM sales_clean").fetchone()[0] == quantity


def test_model_facing_tool_path_also_refuses_writes():
    """模型走的是 `Service.run_tool`，那条路也要拦得住——工具是暴露给模型的。"""
    from kbqa.service import Service

    service = Service()
    before = service.tools.valid_sales_rows()
    result = service.run_tool("run_sql", {"sql": "UPDATE sales_clean SET qty = 0"})
    assert "error" in result, "模型那条路能写数据库：%r" % result
    assert service.tools.valid_sales_rows() == before
