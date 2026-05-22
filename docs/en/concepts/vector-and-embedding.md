# Vector & Embedding

This page explains *why* and *how* SpecStar models vector similarity search.
For the practical recipe, see [How-to: Vector Search](../howto/vector-search.md).

---

## Goals

1. **Define a vector field once** with `Annotated[..., Vector(...)]`.
2. **Two layers**: raw `list[float]` for pre-computed vectors, and
   `Embedding(content, vector, ...)` for content the framework should encode.
3. **Composability**: a vector distance filter is just another condition in
   `ResourceMetaSearchQuery.conditions`; a vector sort is just another sort
   in `ResourceMetaSearchQuery.sorts`. They mix freely with scalar
   conditions and sorts.
4. **Backend-aware**: native pgvector when available, brute-force fallback
   otherwise. Same Python API either way.

---

## Two annotation patterns

### Raw vector

```python
class Doc(Struct):
    embedding: Annotated[list[float], Vector(dim=1536, distance="cosine")]
```

Use when you already have a vector. The framework only validates length and
makes it searchable.

### Embedding wrapper

```python
class Doc(Struct):
    summary: Annotated[
        Embedding,
        Vector(dim=1536, distance="cosine", encoder="openai_small"),
    ]
```

`Embedding` is analogous to `Binary`: a small struct that pairs the source
content with derived metadata (`vector`, `content_hash`, `encoder_id`).
At write time the framework auto-fills the derived fields by calling the
registered encoder.

```python
class Embedding(Struct, kw_only=True):
    content: str
    vector: list[float] | UnsetType = UNSET
    content_hash: str | UnsetType = UNSET   # xxh3_128(content) hex
    encoder_id: str | UnsetType = UNSET     # name from the registry
```

---

## Write pipeline

When you call `create / update / modify` on a model with `Vector` or
`Embedding` fields, the framework runs these steps in order:

1. **Coerce** (`dict` / `Pydantic` → `msgspec.Struct`)
2. **Binary processor** — extract bytes into the blob store (existing behavior)
3. **Embedding processor** — for each `Embedding` field:
   - if `vector` is already set: keep as-is
   - else if the previous revision has the same `(content_hash, encoder_id)`:
     reuse the previous vector (**no encoder call**)
   - else: call the encoder, fill `vector / content_hash / encoder_id`
4. **Dim validator** — raise `ValidationError` if any vector length ≠ `dim`
5. **Encode + persist**

The cache reuse step is the critical optimisation: editing an unrelated field
on a `Doc` does **not** pay another encoding API call.

---

## Query model

Vector primitives live in the same union as scalar primitives:

```python
ResourceMetaSearchQuery(
    conditions=[
        DataSearchCondition(...),         # scalar filter
        DataSearchGroup(...),             # AND/OR/NOT group
        VectorDistanceCondition(...),     # NEW
    ],
    sorts=[
        ResourceMetaSearchSort(...),      # meta field
        ResourceDataSearchSort(...),      # indexed data field
        VectorDistanceSort(...),          # NEW
    ],
)
```

`VectorDistanceCondition` carries `field_path`, `query_vector` (`list[float] |
str`), `operator` (`lt / lte / gt / gte`), `threshold`, and optional `distance`
override.

`VectorDistanceSort` carries `field_path`, `query_vector`, `direction`, and
optional `distance`.

### Query Builder syntax

```python
QB["embedding"].cosine(q) < 0.3              # → VectorDistanceCondition
QB["embedding"].l2(q) > 1.0
QB["embedding"].ip(q) >= 0.7

Query().sort(QB["embedding"].cosine(q))      # → VectorDistanceSort asc
Query().sort(QB["embedding"].cosine(q).desc())
```

`q` is either `list[float]` or `str`. When `str`, the framework calls the
field's registered encoder at search time. Async encoders are not supported
on the sync search path — register a sync encoder for the query side, or
provide both via `vector_encoders`.

---

## Storage model

The source-of-truth vector lives in the resource payload (`IResourceStore`),
serialized along with the rest of the struct via `msgspec`. The meta store
maintains an additional indexable copy:

| Backend | Where the vector lives |
|---|---|
| `postgres` + pgvector | `vector(N)` column per Vector field, HNSW-indexed. Source vector also in JSONB `indexed_data` for parity. |
| Other meta stores | JSONB `indexed_data` only. Search is Python-side brute force. |

`add_model` invokes `ensure_vector_column(field_path, dim, distance)` on the
meta store when it advertises `supports_native_vector_search = True`, which
adds the column and an HNSW index using `CREATE INDEX CONCURRENTLY` (no
table lock).

---

## High-dimensional vectors

pgvector's HNSW index supports up to **2 000 dimensions**. SpecStar accepts
larger annotated dims (e.g. 3 072 for OpenAI `text-embedding-3-large`) and
indexes only the **first 2 000 dimensions**:

- The full vector is still in `IResourceStore` and `indexed_data`.
- The pgvector column is `vector(2000)` and indexed.
- A startup warning highlights this so non-Matryoshka models can be flagged.

This works correctly for Matryoshka-trained embeddings, where the prefix is
itself a valid (lower-resolution) embedding. For models that do not have
this property, prefer dimensions ≤ 2 000.

---

## Distance metrics

| Metric | Annotation value | pgvector operator | Domain |
|---|---|---|---|
| Cosine distance | `"cosine"` (default) | `<=>` | LLM / sentence embeddings |
| Euclidean (L2) | `"l2"` | `<->` | Image / signal vectors |
| Negative inner product | `"ip"` | `<#>` | Pre-normalized vectors |

All three are *distances* — lower means closer — so `VectorDistanceSort
ascending` always returns the nearest rows first regardless of metric.

Resolution: per-call metric > annotation metric > `"cosine"` default.

---

## Backend capability flag

```python
class IMetaStore:
    @property
    def supports_native_vector_search(self) -> bool:
        return False  # subclasses override
```

`PostgresMetaStore` detects the pgvector extension on construction and sets
this to `True`. `ResourceManager` checks the flag when wiring `add_model` and
provisions a pgvector column only when native support is present. The
brute-force code path is wired into `is_match_query` and `get_sort_fn` in
`specstar.resource_manager.basic`.

---

## OpenAPI integration

Vector fields surface as custom extensions on their OpenAPI property:

- `x-vector-dim`: integer
- `x-vector-distance`: `"cosine" | "l2" | "ip"` (omitted when unset)
- `x-vector-encoder-id`: string (omitted when no encoder configured)

The admin UI and downstream SDK generators can use these hints to render
vector-aware controls (e.g. a search-by-text input that POSTs the encoder name
via REST).

---

## What's NOT in V1

- **Multi-vector fields per resource** (`list[Embedding]`) — multi-vector
  indexes need a different strategy on pgvector; treat each as its own
  resource for now.
- **Auto schema migration when `dim` or `distance` changes** — these are
  hard to do safely (data must be re-encoded; index must be rebuilt).
  Bump your schema version and run a backfill instead.
- **GraphQL vector queries** — REST + Python SDK first.
- **Async encoder on the sync query path** — registered async encoders
  work fine on the write path; the query side needs a sync encoder.

---

## See also

- [How-to: Vector Search](../howto/vector-search.md)
- [Search & Indexing](search-indexing.md)
- [Query System](query-system.md)
