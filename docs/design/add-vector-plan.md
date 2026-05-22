# SpecStar Vector + Embedding 實作 Plan

> **狀態**：Plan，未開工
> **Branch**：`add-vector`
> **動機**：把 vector similarity search 變成 SpecStar 的一等公民，並提供 `Embedding(content, vector)` 高階型別自動代算向量

---

## Definition of Done（V1 釋出條件）

- [ ] `Vector(dim, distance, encoder)` annotation 可加在 `list[float]` 或 `Embedding` 欄位
- [ ] `Embedding` 型別與 `Binary` 同層級，寫入時自動 encode、命中 cache 不重算
- [ ] `PostgresMetaStore` 偵測 pgvector 並建立 `vector(N)` 欄 + HNSW 索引
- [ ] 非 pg backend 自動 fallback brute-force，首次 fallback warning
- [ ] QB 支援 `QB["field"].cosine(q) / .l2(q) / .ip(q)`，filter 與 sort 同 expression
- [ ] `q` 為 `list[float]` 或 `str`（後者走 encoder）
- [ ] `VectorDistanceCondition` / `VectorDistanceSort` 可進 `ResourceMetaSearchQuery.conditions` / `.sorts`
- [ ] OpenAPI 注入 `x-vector-dim` / `x-vector-distance` / `x-vector-encoder-id`
- [ ] Admin UI 對 Embedding 欄渲染 text input + search-by-text bar
- [ ] `specstar backfill-vectors --model M --field F` CLI 可批次補資料
- [ ] dim mismatch → `ValidationError("expected dim=N, got M")`
- [ ] 既有 testsuite 零 regression
- [ ] 文件：使用範例 + capability matrix + encoder registry 指南

V2 推遲：GraphQL vector search、`list[Embedding]` multi-vector、completion-aware vector visualizer、並行 backfill。

---

## 設計總覽

### A. 型別系統

兩個層級：

**Level 1：純 Vector（user 自算）**
```python
class Doc(Struct):
    title: str
    embedding: Annotated[list[float], Vector(dim=1536, distance="cosine")]
```

**Level 2：Embedding（framework 自動 encode）**
```python
class Doc(Struct):
    title: str
    summary: Annotated[
        Embedding,
        Vector(dim=1536, distance="cosine", encoder="openai_small"),
    ]
    body: Annotated[Embedding | None, Vector(dim=3072, encoder="openai_large")] = None
```

### B. 新型別

```python
class Vector:
    """Annotation marker. 描述向量欄位的索引/編碼配置。"""
    dim: int                                       # 必填
    distance: Literal["cosine","l2","ip"] | None   # 可選；未提供時走 query default，再無走 cosine
    encoder: str | None                            # 可選；registry name

class Embedding(Struct, kw_only=True):
    content: str
    vector: list[float] | UnsetType = UNSET
    content_hash: str | UnsetType = UNSET          # xxh3_128(content)，hex string
    encoder_id: str | UnsetType = UNSET            # 寫入時使用的 encoder name

# Query schema 擴充
class VectorDistanceCondition(Struct, kw_only=True, tag=True):
    field_path: str
    query_vector: list[float] | str                # str → 走 encoder
    operator: DataSearchOperator                   # 限 lt/lte/gt/gte
    threshold: float
    distance: Literal["cosine","l2","ip"] | None = None

class VectorDistanceSort(Struct, kw_only=True, tag=True):
    field_path: str
    query_vector: list[float] | str
    direction: ResourceMetaSortDirection = ascending
    distance: Literal["cosine","l2","ip"] | None = None
```

`conditions` 與 `sorts` 的 union 型別擴充以接受上述兩者。

### C. QB 語法

```python
# Filter
QB["embedding"].cosine(q) < 0.3
QB["embedding"].l2(q) < 1.0
QB["embedding"].ip(q) > 0.7

# Sort
.sort(QB["embedding"].cosine(q))            # 升冪
.sort(QB["embedding"].cosine(q).desc())     # 降冪

# 組合
((QB["doctype"] == "abc") & (QB["vec"].cosine(q) < 0.3)) \
    .sort(QB["vec"].cosine(q)).limit(10)

# Embedding 欄位 implicit unwrap：
QB["summary"].cosine(q)                      # 自動視為 summary.vector
```

實作：`Field.cosine/l2/ip` 回傳 `VectorDistanceExpr`，dunder operator → `VectorDistanceCondition`；直接丟進 `.sort(...)` → `VectorDistanceSort`。

### D. Encoder Registry

三層優先序，**底層覆蓋上層**：

| Level | API |
|---|---|
| Global  | `spec.configure(vector_encoders={"openai_small": fn, ...})` |
| Model   | `spec.add_model(Doc, vector_encoders={"summary": "openai_small"})` |
| Field   | `Vector(..., encoder="openai_small")` |

Encoder 簽名：`Callable[[str], list[float]] | Callable[[str], Awaitable[list[float]]]`，sync / async 都支援。

### E. 儲存模型（PostgresMetaStore + pgvector）

| 來源 | 儲存位置 | 用途 |
|---|---|---|
| 完整 `list[float]` 或 `Embedding(content, vector, ...)` | `IResourceStore`（msgspec 序列化進 struct） | source of truth、export、重建索引 |
| `vector(min(dim, 2048))` 副本 | `PostgresMetaStore` 新增的 vector 欄 | pgvector HNSW 索引、ANN 查詢 |

- `dim > 2048`：截前 2048 維進 pg；`add_model` log warning（Matryoshka 模型適用）
- HNSW 索引建立用 `CREATE INDEX CONCURRENTLY` 避免鎖表
- `vector_cosine_ops` / `vector_l2_ops` / `vector_ip_ops` 依 distance 而定

### F. Backend Capability 矩陣

| Backend | 行為 |
|---|---|
| postgres + pgvector | native `vector(N)` + HNSW + `<=>` / `<->` / `<#>` SQL |
| postgres（無 pgvector） | `add_model` 時 raise，要求安裝擴充 |
| memory / disk / sqlite / redis / df / sqlalchemy / fast_slow | vector 進 `indexed_data` JSONB；查詢走 Python brute-force（O(n)）；首次 fallback emit `UserWarning`（per process per model） |

`IMetaStore.supports_native_vector_search: bool` capability flag 提供給 ResourceManager 決定翻譯路徑。

### G. 寫入 Pipeline

新增 `EmbeddingProcessor`，與 `BinaryProcessor` 並列、用 type-driven traversal：

```
1. _coerce_data → msgspec.Struct
2. EmbeddingProcessor.process(data):
   for each Embedding field:
     if vector is provided:
         validate dim → raise on mismatch
     else (need encode):
         new_hash = xxh3_128(content).hexdigest()
         prev = read_previous_revision()  # update / modify only
         if prev.content_hash == new_hash and prev.encoder_id == current_encoder_id:
             reuse prev.vector
         else:
             vector = await encoder(content)   # raise on failure → entire write fails
             content_hash = new_hash
             encoder_id = current_encoder_id
3. VectorProcessor.process(data):
   for each list[float] + Vector field:
     validate dim
4. ResourceManager.save:
   - full struct → IResourceStore
   - vector 副本（前 min(dim, 2048) 維）→ pg vector column
```

`content_hash` 用 **xxh3_128**：non-cryptographic 但 collision space = 2^128，速度與 xxh3_64 等同，足夠避免「碰撞 → 跳過 encoder → 留舊向量」的 silent bug。

### H. 查詢 Pipeline

```
1. build_query parses input → ResourceMetaSearchQuery（含 VectorDistance* tags）
2. 解析 query_vector：
   if isinstance(query_vector, str):
       resolve encoder for field → await encoder(text) → list[float]
3. 解析 distance：condition/sort 給的 > annotation 給的 > "cosine"
4. 翻譯到 backend：
   pg + pgvector:  WHERE ... AND col <=> %s < threshold ORDER BY col <=> %s ASC LIMIT k
   brute-force:     Python 端讀全部 meta → 算距離 → 排序 → limit
```

### I. DDL / Migration

| 動作 | DDL | 資料 |
|---|---|---|
| 新增 Vector / Embedding 欄 | `add_model` 自動 `ALTER TABLE ADD COLUMN` + `CREATE INDEX CONCURRENTLY` | 舊 row vector 為 NULL；查詢自然排除；使用者要 backfill 跑 CLI |
| 改 dim | `add_model` 偵測 column 既有 dim 不一致 → **raise**，要求顯式 schema version 升版 | 重算 embedding 為 user 職責 |
| 改 distance | 同上 → raise；要求顯式新 schema version | 不需重算，但要 drop+recreate index |
| 刪除欄位 | log warning，**不 auto drop**（保護資料）；要求手動 ALTER | — |

### J. REST API

- **不另開端點**。沿用 `GET /{model}` query string 機制
- vector 欄位太大要塞進 URL → 使用者改傳 `query_vector` 為 `str`，由 encoder 編碼（內部 vector 但網路上的 query 字串只是短文字）

### K. Validator

`add_model` 註冊時自動生成 `_VectorDimValidator`，掛進 IValidator chain：
- 長度 ≠ `dim` → `ValidationError("Vector field 'X': expected dim=N, got M")`
- pure `list[float]` 欄與 `Embedding.vector` 子欄都檢查

### L. OpenAPI / Web

- OpenAPI 注入 `x-vector-dim`, `x-vector-distance`, `x-vector-encoder-id` 自訂屬性
- Admin UI：
  - Embedding 欄渲染為 text input（content 編輯，vector/hash/encoder_id 隱藏）
  - 加 search bar：text → 走 encoder → vector search
  - pure Vector 欄維持 read-only，僅能透過 search bar 觸發查詢

### M. Backfill CLI

```bash
specstar backfill-vectors --model Doc --field summary
```

- 對 Embedding 欄位：掃 `vector IS NULL OR encoder_id != current` 的 rows → call encoder(content) → update
- 對 pure `list[float] + Vector` 欄位：不支援（沒有 source 可重算）
- V1 單緒、loop；批次大小 / 並行 / progress bar 是 V2

---

## 依賴拓樸

```
Phase 1：Annotation 與型別
├─ 1.1 Vector marker
├─ 1.2 Embedding struct
└─ 1.3 extract_vectors / extract_embeddings 工具

Phase 2：寫入 Pipeline
├─ 2.1 _VectorDimValidator 自動掛載
├─ 2.2 EmbeddingProcessor（traversal + cache reuse with xxh3_128）
└─ 2.3 Encoder registry（global / model / field）

Phase 3：Query 表達
├─ 3.1 VectorDistanceCondition / VectorDistanceSort schema
├─ 3.2 QB Field.cosine/l2/ip
└─ 3.3 build_query 整合（含 str→vector 編碼）

Phase 4：Postgres backend
├─ 4.1 pgvector capability 偵測
├─ 4.2 ALTER TABLE / CREATE INDEX CONCURRENTLY at add_model
├─ 4.3 SQL 翻譯（filter + sort）
└─ 4.4 dim>2048 截斷邏輯

Phase 5：Brute-force fallback
├─ 5.1 IMetaStore.supports_native_vector_search flag
├─ 5.2 Python 距離函式（cosine/l2/ip）
└─ 5.3 ResourceManager.search 翻譯時依 capability 切換

Phase 6：使用者邊界
├─ 6.1 OpenAPI 注入
├─ 6.2 Admin UI 渲染
└─ 6.3 backfill-vectors CLI

Phase 7：文件與測試
├─ 7.1 Capability matrix doc
├─ 7.2 Encoder registry / migration guide
└─ 7.3 Integration test（真 pg + pgvector，gated on env var）
```

---

## 已決定的關鍵點（grilling 結果摘要）

- **Annotation marker name**：`Vector`（不是 `Embedding`），名實相符
- **dim 超過 pgvector HNSW 上限（2048）**：靜默截前 2048 維進索引欄、log warning；完整 vector 仍存在 IResourceStore（Matryoshka 模型適用）
- **distance 預設**：annotation > query > "cosine"
- **dim mismatch**：寫入時 raise `ValidationError`，訊息含 expected / actual
- **REST URL 太長**：不另開 POST，使用者改傳 string 給 encoder 編碼
- **Vector / Embedding 同層**：Embedding 是 struct（content + vector + hash + encoder_id），Vector annotation 在兩種欄位上語意一致
- **Cache reuse**：`(content_hash, encoder_id)` 同時不變才重用，避免 encoder 切換漏算
- **Encoder error**：寫入 atomic、整個 fail；查詢同樣 raise
- **content_hash 算法**：xxh3_128（speed of xxh3，128-bit collision safety）
- **Content 存哪**：inline 進 resource data，不寫進 blob store
- **QB API**：`Field.cosine(q) / .l2(q) / .ip(q)` 三個方法，filter/sort 同 expression
- **Backend fallback**：非 pgvector 走 brute-force，首次觸發 warning
- **Capability check**：三段（store init / add_model / query），有 `supports_native_vector_search` flag
- **Migration**：auto add column；改 dim/distance raise；刪欄不 auto drop
- **V1 包含**：OpenAPI 注入、Admin UI 渲染、backfill CLI
- **V2 推遲**：GraphQL vector、list[Embedding] multi-vector、並行 backfill

---

## 開放問題（實作期再敲）

- HNSW 參數（`m`, `ef_construction`）：先用 pgvector 預設，未來透過 backend config 調整
- Encoder registry 在 `BackendConfig` 還是 `SpecStar.configure()`：傾向後者
- xxhash 套件依賴：`xxhash` PyPI package（C 實作，extremely fast）加進 `pyproject.toml`
- pg `CREATE INDEX CONCURRENTLY` 必須不在 transaction 中執行；要與 `_init_postgres_table` 既有 transaction 路徑切開
- `query_vector: str` 路徑的 encoder 失敗：與寫入一致 → raise 整個查詢失敗

---

## 風險

- **pgvector 安裝門檻**：需 superuser 才能 `CREATE EXTENSION`。dev 用 docker-compose 內建 image；prod 由 DBA 預先處理
- **大量 backfill 時的 API 費用**：CLI 應加 `--dry-run` 預估 token 量；未來支援 batch encoder
- **encoder switching 的破壞性**：encoder_id 改變 = 重算所有 embedding。文件需強調此成本
- **Matryoshka 隱式截斷誤用**：若 user 用非 Matryoshka 模型（e.g. word2vec 拼接的 3000 維）會默默損失精度。靠 startup warning + 文件強調

---

## 與既有設計的相容性

- 完全使用既有的 `IMetaStore`、`IResourceStore`、`IValidator`、`IndexedValueExtractor` 抽象，沒有破壞性修改
- `ResourceMetaSearchQuery` 的 union 擴充屬於 backwards-compatible（既有 client 不送 vector 條件就完全等價）
- `BinaryProcessor` 與 `EmbeddingProcessor` 互不影響，可並存於同一 model
- `Schema` migration API 不變；vector 欄位的 dim/distance 變動納入既有的 schema version 機制
