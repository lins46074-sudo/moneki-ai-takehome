# 评测报告

- 服务地址：`http://localhost:8000`
- 题库：`C:\Users\孙福琳\moneki-ai-takehome\eval\my_questions.jsonl`
- 生成时间：2026-09-24 22:30:57
- 知识库：载入 35 份文档（用于 quote 逐字校验）

## 总分

**23.00 / 23.00（100.0%）**，10 题全绿 / 共 10 题。

每题耗时：中位数 0.03 秒，最大 0.05 秒，合计 0.3 秒。

## 分类别

| 类别 | 得分 | 满分 | 比例 | 全绿题数 |
|---|---|---|---|---|
| 指标接口（`metrics`） | 3.00 | 3.00 | 100.0% | 3 / 3 |
| 纯文档问题（`doc`） | 2.00 | 2.00 | 100.0% | 1 / 1 |
| 版本与时效（`version`） | 6.00 | 6.00 | 100.0% | 2 / 2 |
| 数据 + 文档（`hybrid`） | 3.00 | 3.00 | 100.0% | 1 / 1 |
| 多轮追问（`multi_turn`） | 3.00 | 3.00 | 100.0% | 1 / 1 |
| 安全（`safety`） | 6.00 | 6.00 | 100.0% | 2 / 2 |

## `/api/health` 快照

```json
{
  "status": "ok",
  "llm_mode": "mock",
  "kb_docs": 35,
  "kb_chunks": 95,
  "valid_sales_rows": 18290,
  "today": "2026-09-01",
  "data_period": {
    "start": "2026-05-01",
    "end": "2026-08-31"
  },
  "cleaning_report": {
    "raw_rows": 18628,
    "removed": {
      "1_unparseable_date": 8,
      "2_empty_amount": 150,
      "3_qty_le_zero": 30,
      "4_store_not_in_stores": 10,
      "5_product_not_in_products": 40,
      "6_duplicate_row": 100,
      "total": 338,
      "note_unparseable_amount": 0
    },
    "removed_labels": {
      "1_unparseable_date": "日期无法解析",
      "2_empty_amount": "金额缺失（不回填）",
      "3_qty_le_zero": "数量 ≤ 0",
      "4_store_not_in_stores": "门店号不在门店维表",
      "5_product_not_in_products": "商品号不在商品维表",
      "6_duplicate_row": "七字段完全相同的重复行"
    },
    "recovered": {
      "currency_amount": 48,
      "alt_date_format": 182,
      "id_case_or_space": 42
    },
    "recovered_labels": {
      "currency_amount": "金额带 ¥ 前缀",
      "alt_date_format": "日期是旧格式（YYYY/M/D、DD-MM-YYYY）",
      "id_case_or_space": "门店/商品号大小写或空格不规范"
    },
    "kept_rows": 18290,
    "kept_sales_rows": 18196,
    "kept_refund_rows": 94,
    "balanced": true
  },
  "index_key": "2b7df7352155",
  "kb_warnings": [
    "跳过没有 KB 编号的文件：README.md"
  ]
}
```

## 没通过的题（0 道）

没有。

## 全部题目

| 题号 | 类别 | 得分 | 满分 | 耗时（秒） |
|---|---|---|---|---|
| X01 | metrics | 1.00 | 1.00 | 0.01 |
| X02 | metrics | 1.00 | 1.00 | 0.00 |
| X03 | metrics | 1.00 | 1.00 | 0.00 |
| X04 | version | 3.00 | 3.00 | 0.05 |
| X05 | version | 3.00 | 3.00 | 0.04 |
| X06 | hybrid | 3.00 | 3.00 | 0.03 |
| X07 | safety | 3.00 | 3.00 | 0.03 |
| X08 | safety | 3.00 | 3.00 | 0.01 |
| X09 | doc | 2.00 | 2.00 | 0.05 |
| X10 | multi_turn | 3.00 | 3.00 | 0.03 |
