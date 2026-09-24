"""把原始 sales 按 KB-001 清洗后导进 var/clean.db，指标都查这张表。

清洗分两步，顺序不能颠倒（KB-001 §2 在前、§3 在后）：

1. **规范化**——把可恢复的脏写法统一成标准写法。`¥38.00` 与 `38.00` 是同一个
   金额，`s01`、`S01 `、` s03` 是同一家门店，`2026/6/1`、`25-07-2026` 是同一
   个日期。这一步只做转换，不丢行。
2. **剔除**——按 §3 的六条依次判断，每条各记一笔台账，供数据质量面板展示。

顺序反了的代价在 KB-001 §7.2 里写得很直接：先判断脏外键再规范化，会把真实订单
误删。所以这里严格按「先规范化、后剔除」实现。
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Optional

#: 金额里的 `¥`、`￥` 与各类空白去掉再按数字解析（KB-001 §2.3）。带符号的行是可恢复的，必须保留。
_CURRENCY = str.maketrans("", "", "¥￥ \t　")

#: KB-001 §2.2 的三种日期写法。第三种是旧 POS 导出格式，**日在前、月在后**：
#: `25-07-2026` 是 2026 年 7 月 25 日。模式里都留了「日大于 12」的样本做验证。
_ISO_DATE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_SLASH_DATE = re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})$")
_DAY_FIRST_DATE = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})$")

#: §3 的六条剔除规则，键名进台账，顺序即执行顺序。
REMOVAL_REASONS = (
    "1_unparseable_date",
    "2_empty_amount",
    "3_qty_le_zero",
    "4_store_not_in_stores",
    "5_product_not_in_products",
    "6_duplicate_row",
)

#: 面板直接展示的中文标签，避免前端再硬编码一份。
REMOVAL_LABELS = {
    "1_unparseable_date": "日期无法解析",
    "2_empty_amount": "金额缺失（不回填）",
    "3_qty_le_zero": "数量 ≤ 0",
    "4_store_not_in_stores": "门店号不在门店维表",
    "5_product_not_in_products": "商品号不在商品维表",
    "6_duplicate_row": "七字段完全相同的重复行",
}

#: 可恢复的脏写法统计：这些行**没有被剔除**，只是被修正后继续参与统计。
RECOVERED_LABELS = {
    "currency_amount": "金额带 ¥ 前缀",
    "alt_date_format": "日期是旧格式（YYYY/M/D、DD-MM-YYYY）",
    "id_case_or_space": "门店/商品号大小写或空格不规范",
}


def parse_date(value: Optional[str]) -> Optional[str]:
    """按 KB-001 §2.2 解析日期，返回 ISO 字符串；三种格式都不匹配时返回 None。

    `DD-MM-YYYY` 与 `YYYY/M/D` 在字符串排序下和 ISO 完全对不上，必须先统一成
    ISO，后面的区间筛选才能直接比字符串。
    """
    text = (value or "").strip()
    if not text:
        return None
    for pattern, order in (
        (_ISO_DATE, "ymd"),
        (_SLASH_DATE, "ymd"),
        (_DAY_FIRST_DATE, "dmy"),
    ):
        match = pattern.match(text)
        if not match:
            continue
        year, month, day = (match.group(1), match.group(2), match.group(3))
        if order == "dmy":
            day, month, year = year, month, day
        try:
            return date(int(year), int(month), int(day)).isoformat()
        except ValueError:
            return None
    return None


def parse_amount(value: Optional[str]) -> tuple[Optional[int], str]:
    """返回 (分, 状态)。状态取值：`ok`、`empty`、`bad`。

    KB-001 §2.3 与 §3.2：`¥38.00` 与 `38.00` 是同一个金额；空金额直接剔除，**不回填**。
    """
    text = (value or "").translate(_CURRENCY)
    if not text:
        return None, "empty"
    try:
        cents = int((Decimal(text) * 100).to_integral_value())
    except (InvalidOperation, ValueError):
        return None, "bad"
    return cents, "ok"


def parse_qty(value: Optional[str]) -> Optional[int]:
    """KB-001 §2.4：按整数解析。解析不了的返回 None，会被 §3.3 剔除。"""
    text = (value or "").strip()
    if not text:
        return None
    try:
        return int(Decimal(text))
    except (InvalidOperation, ValueError):
        return None


def normalize_id(value: Optional[str]) -> str:
    """KB-001 §2.1：去掉首尾空白并转大写。"""
    return (value or "").strip().upper()


@dataclass
class CleaningReport:
    """清洗台账：`/api/health` 与数据质量面板都用它。"""

    raw_rows: int = 0
    kept_rows: int = 0
    kept_sales_rows: int = 0
    kept_refund_rows: int = 0
    removed: dict[str, int] = field(default_factory=lambda: {k: 0 for k in REMOVAL_REASONS})
    note_unparseable_amount: int = 0
    #: 被修正后保留的脏写法计数（§2 的规范化动作）。
    recovered: dict[str, int] = field(default_factory=lambda: {k: 0 for k in RECOVERED_LABELS})

    def as_dict(self) -> dict:
        removed_total = sum(self.removed.values())
        return {
            "raw_rows": self.raw_rows,
            "removed": dict(
                self.removed,
                total=removed_total,
                note_unparseable_amount=self.note_unparseable_amount,
            ),
            "removed_labels": dict(REMOVAL_LABELS),
            "recovered": dict(self.recovered),
            "recovered_labels": dict(RECOVERED_LABELS),
            "kept_rows": self.kept_rows,
            "kept_sales_rows": self.kept_sales_rows,
            "kept_refund_rows": self.kept_refund_rows,
            # 校验用：原始行数 = 保留行数 + 剔除行数。
            "balanced": self.raw_rows == self.kept_rows + removed_total,
        }


def open_readonly(path: Path) -> sqlite3.Connection:
    """打开数据库。"""
    conn = sqlite3.connect(path.as_posix(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def clean_rows(
    rows: Iterable[sqlite3.Row], store_ids: set[str], product_ids: set[str]
) -> tuple[list[tuple], CleaningReport]:
    """按 KB-001 §2、§3 清洗明细行，返回（保留的行, 台账）。

    保留的行统一为规范写法：日期 ISO、门店/商品号大写、金额按分存整数。
    """
    report = CleaningReport()
    kept: list[tuple] = []
    seen: set[tuple] = set()

    for row in rows:
        report.raw_rows += 1

        # -- §2 规范化：只转换，不丢行 ------------------------------------------
        raw_date = (row["date"] or "").strip()
        raw_amount = row["amount"] or ""
        raw_store = row["store_id"] or ""
        raw_product = row["product_id"] or ""

        day = parse_date(raw_date)
        cents, status = parse_amount(raw_amount)
        qty = parse_qty(row["qty"])
        store_id = normalize_id(raw_store)
        product_id = normalize_id(raw_product)

        if status == "bad":
            # §3.2 只写了「金额为空」，解析不出来的按同样理由处理，另记一笔备查。
            report.note_unparseable_amount += 1

        # 本行被修正过哪些脏写法，等它通过全部剔除规则之后再记进台账——
        # 台账要说的是「修好之后继续参与统计的有多少行」，不是「扫到过多少处脏」。
        recovered = (
            ("alt_date_format", day is not None and day != raw_date),
            ("currency_amount", "¥" in raw_amount or "￥" in raw_amount),
            ("id_case_or_space", store_id != raw_store or product_id != raw_product),
        )

        # -- §3 剔除：按顺序判断，第一条命中就记台账并跳过本行 --------------------
        if day is None:
            report.removed["1_unparseable_date"] += 1
            continue
        if cents is None:
            report.removed["2_empty_amount"] += 1
            continue
        if qty is None or qty <= 0:
            report.removed["3_qty_le_zero"] += 1
            continue
        if store_id not in store_ids:
            report.removed["4_store_not_in_stores"] += 1
            continue
        if product_id not in product_ids:
            report.removed["5_product_not_in_products"] += 1
            continue

        order_id = (row["order_id"] or "").strip()
        payment = (row["payment"] or "").strip()
        # §3.6 / §4：完全相同的七字段才是重复行；共用订单号的不同商品行必须保留。
        signature = (order_id, day, store_id, product_id, qty, cents, payment)
        if signature in seen:
            report.removed["6_duplicate_row"] += 1
            continue
        seen.add(signature)

        for key, hit in recovered:
            if hit:
                report.recovered[key] += 1

        kept.append(
            (
                order_id,
                day,
                store_id,
                product_id,
                qty,
                cents,
                payment,
                1 if cents < 0 else 0,
            )
        )

    report.kept_rows = len(kept)
    report.kept_refund_rows = sum(1 for row in kept if row[-1])
    # §4 的销售行是 amount > 0；金额为 0 的行两边都不算，只留在表里。
    report.kept_sales_rows = sum(1 for row in kept if row[5] > 0)
    return kept, report


_SCHEMA = """
CREATE TABLE stores (store_id TEXT PRIMARY KEY, store_name TEXT, category TEXT, district TEXT);
CREATE TABLE products (product_id TEXT PRIMARY KEY, product_name TEXT,
                       product_category TEXT, unit_price REAL);
CREATE TABLE sales_clean (
    order_id TEXT, date TEXT, store_id TEXT, product_id TEXT,
    qty INTEGER, amount_cents INTEGER, payment TEXT, is_refund INTEGER
);
CREATE INDEX idx_clean_date ON sales_clean(date);
CREATE INDEX idx_clean_store ON sales_clean(store_id);
CREATE INDEX idx_clean_product ON sales_clean(product_id);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""


def build_clean_db(source: Path, target: Path) -> CleaningReport:
    """从只读的源库重建清洗表。返回清洗台账，供 `/api/health` 与数据质量面板使用。"""
    if not source.exists():
        raise FileNotFoundError("找不到源数据库：%s" % source)
    src = open_readonly(source)
    try:
        stores = [
            tuple(r)
            for r in src.execute("SELECT store_id, store_name, category, district FROM stores")
        ]
        products = [
            tuple(r)
            for r in src.execute(
                "SELECT product_id, product_name, product_category, unit_price FROM products"
            )
        ]
        # 维表自身也规范化一次：不然 `p06` 这种写法会把它自己的商品判成脏外键。
        store_ids = {normalize_id(row[0]) for row in stores}
        product_ids = {normalize_id(row[0]) for row in products}
        stores = [(normalize_id(r[0]),) + tuple(r[1:]) for r in stores]
        products = [(normalize_id(r[0]),) + tuple(r[1:]) for r in products]
        rows, report = clean_rows(
            src.execute("SELECT order_id, date, store_id, product_id, qty, amount, payment FROM sales"),
            store_ids,
            product_ids,
        )
    finally:
        src.close()

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        try:
            target.unlink()
        except PermissionError as exc:
            # Windows 下服务在跑时会占着这个文件。原始报错只有一行 WinError 32，
            # 看不出该做什么，这里换成能直接照做的提示。
            raise RuntimeError(
                "无法覆盖 %s：文件正被占用。服务还在运行时请先停掉它，再执行重建。" % target
            ) from exc
    out = sqlite3.connect(target)
    try:
        out.executescript(_SCHEMA)
        out.executemany("INSERT INTO stores VALUES (?,?,?,?)", stores)
        out.executemany("INSERT INTO products VALUES (?,?,?,?)", products)
        out.executemany("INSERT INTO sales_clean VALUES (?,?,?,?,?,?,?,?)", rows)
        out.execute(
            "INSERT INTO meta VALUES ('cleaning_report', ?)",
            (json.dumps(report.as_dict(), ensure_ascii=False),),
        )
        out.execute("INSERT INTO meta VALUES ('source_db', ?)", (source.name,))
        out.commit()
    finally:
        out.close()
    return report
