# exp_aggregate_by 群組層級 order_by + limit/offset 分頁 — 實作 Plan

> **狀態**:實作中(in-process reference DONE,commit `201571a`)
> **Branch**:`issue-412-aggregate-group-pagination`
> **Issue**:[#412](https://github.com/HYChou0515/specstar/issues/412)
> **動機**:`exp_aggregate_by(by, aggregates, query=None)` 目前回**所有** group、無序。`IMetaWithAgg.aggregate_by` 明確忽略 `query.limit/offset`(「paging an aggregate is meaningless」——對 *row-level* 分頁正確),但沒有辦法 **order + 分頁 GROUP 結果本身**。下游 ai-workspace #511「依概念分組」待審 inbox 要對 distinct `cluster_key` 依「最新成員時間」分頁;沒有 group-level 分頁,消費端就得把每個 group 撈進 Python 排序切片 = O(all-groups) 全載入,正是要避免的。

---

## Definition of Done

- [ ] `exp_aggregate_by(..., *, order_by=None, limit=None, offset=0)` — keyword-only,group-level 排序 + 分頁
- [ ] `order_by` 接**聚合 result-name**(如 `"-latest"` 對應 `{"latest": Max(...)}`)或 **group key sentinel `"key"`**;沿用 `Query.sort()` 的 `"-name"`/`"+name"` 方向慣例(asc 預設、`-` = desc);目標非聚合名也非 `"key"` → raise
- [ ] tie-break = **group key 升序**(穩定次序,pages 穩定);NULL 一律 **NULLS LAST**(order value 與 key tiebreak 皆是)
- [ ] `exp_count_groups(by, query=None) -> int` distinct-group 總數(pager 的 total),**不受**該 call 的 limit/offset 影響
- [ ] `Count / Sum / Min / Max / Avg` **全部下推**成引擎 GROUP BY(才能當 ORDER BY 目標);`ForeignAggregate` 仍 Python(per-key 子查詢)
- [ ] `order_by` 目標可下推(`"key"` 或 scalar self-aggregate)→ `ORDER BY … LIMIT … OFFSET` 整段下推;目標是 `ForeignAggregate`(Python-only)→ **退回 in-process** order+paginate
- [ ] NULLS LAST 用 `(col IS NULL) ASC, col <dir>` 前綴技巧(免版本依賴、SQLite/PG/in-process 三者一致)
- [ ] **SQLite** 真下推
- [ ] **Postgres** 真下推(#511 線上跑 multipod 共用 PG,只有 PG 真下推 grouped 生產才是 O(page))
- [ ] 跨後端 **parity**:in-process ≡ sqlite ≡ pg,同一組 parametrized 斷言全過(pushed 結果 MUST == in-process reduction)
- [ ] 既有 testsuite 零 regression;ruff / type 綠;CHANGELOG `[Unreleased]`

---

## 定案設計(grill 結論)

**API**(reference 已 commit)
```python
def exp_aggregate_by(
    self, by, aggregates, query=None, *,
    order_by: str | None = None,   # 聚合 result-name 或 "key"(group key sentinel)
    limit: int | None = None,      # 分頁 GROUP(非 row-level query.limit/offset)
    offset: int = 0,
) -> list[GroupRow]: ...

def exp_count_groups(self, by, query=None) -> int: ...   # distinct-group 總數
```

**排序語意**(reference 已定,pushdown 必須逐字對齊)
- 主鍵 = `order_by` 目標(聚合值或 key),方向由 `+`/`-` 決定。
- 次鍵 = **group key 升序**(穩定 tie-break;Python reference 靠 stable sort 兩段排實現)。
- NULL 一律墊底:in-process 用 `(x is None, x)`;SQL 用 `(col IS NULL) ASC, col <dir>` 前綴 —— 三後端一致,與各引擎 NULL 預設無關。
- `order_by` 目標非法(不是聚合名也不是 `"key"`)→ raise;`offset/limit` 負值 → raise。

**下推 vs fallback 規則**
- `order_by` 目標可下推(`"key"` 或 scalar self-aggregate:Count/Sum/Min/Max/Avg)→ WHERE(row-level query)→ GROUP BY → 群層 `ORDER BY … LIMIT … OFFSET` 全下推引擎。
- `order_by` 目標是 `ForeignAggregate`(Python-only)→ 整段**退回 in-process**(算全群→排序→切片),保正確。
- 後端未實作 `IMetaWithAgg` → in-process fallback(結果仍須 == reference)。

**後端範圍**:SQLite 真下推 + Postgres 真下推 + in-process reference(正確性基準)三者 parity 強制一致。

---

## Phases(對應 tasks #36–39)

1. **in-process reference**(**DONE**,commit `201571a`):在 groups dict 建好後,依 named aggregate / `"key"` 排序 `GroupRow`s(NULLS LAST + key tiebreak)、切片,加 `exp_count_groups`;`tests/meta_store/test_aggregate_by.py::TestAggregateByOrderAndPaginate` 跨 memory/disk/sqlite/pg parametrize。**此路徑是跨後端正確性參考**,pushdown 必須 match。
2. **SQLite pushdown**:`IMetaWithAgg.aggregate_by` 加 order/limit/offset;Count/Sum/Min/Max/Avg 進引擎 GROUP BY;`(col IS NULL)` 前綴 + key tiebreak;order_by 為 ForeignAggregate → 不下推(fallback)。
3. **Postgres pushdown / parity**:同語意下推到 PG。
4. **跨後端 parity 收尾**:`@pytest.mark.parametrize` 同一組斷言跑 memory / disk / sqlite / pg,結果逐一相同;ruff / type;PR。

---

## 下游對接(為什麼要做)

ai-workspace #511 grouped 待審 inbox:
```python
rm.exp_aggregate_by(
    QB["cluster_key"],
    {"n": Count(), "latest": Max(QB.created_time())},
    query=(collection & state=="active" & kind∈{proposal, term_question}),
    order_by="-latest", offset=o, limit=n,
)
# + rm.exp_count_groups(QB["cluster_key"], query=...) 給 pager total
```
→ 一頁只回 N 個概念(依最新成員時間),消費端再 `cluster_key IN (當頁)` 載成員,不再 O(all-groups)。
