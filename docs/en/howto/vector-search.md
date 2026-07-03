# Vector Search & Embeddings

SpecStar provides first-class support for vector similarity search via the
`Vector` annotation and the `Embedding` struct type. This guide shows the
common patterns end-to-end.

---

## TL;DR

```python
from typing import Annotated

from msgspec import Struct

from specstar import Embedding, SpecStar, Vector
from specstar.query import QB


class Doc(Struct):
    title: str
    doctype: str
    summary: Annotated[Embedding, Vector(dim=1536, encoder="openai_small")]


def embed(text: str) -> list[float]:
    # call your favorite embedding model — returns a 1536-d vector
    ...


spec = SpecStar()
spec.configure(vector_encoders={"openai_small": embed})
# `doctype` is a regular indexed scalar so we can combine it with the
# vector filter below.
spec.add_model(Doc, indexed_fields=["doctype"])
mgr = spec.get_resource_manager(Doc)

# Write: vector is auto-computed from content
mgr.create(
    Doc(title="hello", doctype="article",
        summary=Embedding(content="long doc text..."))
)

# Query: nearest-3 by cosine, with a doctype filter, using a plain string query
query = (
    (QB["doctype"] == "article") & (QB["summary"].cosine("how to use ...") < 0.3)
).sort(QB["summary"].cosine("how to use ...")).limit(3).build()

results = mgr.list_resources(query, returns=["data"])
```

---

## 1. Two ways to declare a vector field

### Level 1 — raw `list[float]` (you compute the vector yourself)

```python
class Doc(Struct):
    title: str
    embedding: Annotated[list[float], Vector(dim=1536, distance="cosine")]


mgr.create(Doc(title="t", embedding=my_vector))
```

Use this when your application already has vectors and you don't want SpecStar
to call any encoder.

### Level 2 — `Embedding` struct (framework calls the encoder)

```python
class Doc(Struct):
    title: str
    summary: Annotated[
        Embedding,
        Vector(dim=1536, distance="cosine", encoder="openai_small"),
    ]


mgr.create(Doc(title="t", summary=Embedding(content="...")))
```

`Embedding(content="...")` is enough — the framework runs the registered encoder,
fills in `vector`, `content_hash` (xxh3_128), and `encoder_id`.

If `content` is unchanged on a subsequent `update()`, the encoder is **not**
re-called (cache reuse based on `(content_hash, encoder_id)`).

---

## 2. Registering encoders

SpecStar does **not** ship with any embedding model. You bring your own
callable that takes `str` and returns `list[float]` of the dimension you
declared on the `Vector` annotation. The framework only enforces the contract
— `dim` must match, that's it.

### 2a. Wiring popular providers

**OpenAI** (1536-d `text-embedding-3-small`, 3072-d `text-embedding-3-large`):

```python
from openai import OpenAI

_client = OpenAI()  # uses OPENAI_API_KEY env var

def embed_openai_small(text: str) -> list[float]:
    resp = _client.embeddings.create(model="text-embedding-3-small", input=text)
    return resp.data[0].embedding


# Async variant (works on the write path)
from openai import AsyncOpenAI

_aclient = AsyncOpenAI()

async def embed_openai_small_async(text: str) -> list[float]:
    resp = await _aclient.embeddings.create(
        model="text-embedding-3-small", input=text,
    )
    return resp.data[0].embedding
```

**sentence-transformers** (local; no API key, ~90 MB download for the small one):

```python
from sentence_transformers import SentenceTransformer

_model = SentenceTransformer("all-MiniLM-L6-v2")  # 384-d

def embed_local(text: str) -> list[float]:
    return _model.encode(text, convert_to_numpy=False).tolist()
```

**Cohere**, **VoyageAI**, **Mistral embed**, etc. all follow the same shape —
wrap their SDK call in a function with signature `(str) -> list[float]`.

**HuggingFace inference API** when you don't want a local model:

```python
import os
import requests

_HF_TOKEN = os.environ["HF_TOKEN"]
_HF_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

def embed_hf(text: str) -> list[float]:
    r = requests.post(
        f"https://api-inference.huggingface.co/pipeline/feature-extraction/{_HF_MODEL}",
        headers={"Authorization": f"Bearer {_HF_TOKEN}"},
        json={"inputs": text},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()
```

!!! note "Test code uses tiny deterministic stubs"
    The unit test suite registers small functions like `lambda t: [1.0, 0.0]`
    so behavior is reproducible without paying for API calls or downloading
    model weights. Replace those with the real wiring above for production.

### 2b. Registration hierarchy

Encoders are `Callable[[str], list[float]]` (sync) or
`Callable[[str], Awaitable[list[float]]]` (async, write path only).

Resolution priority — **inner overrides outer**:

```python
# 1. Global (least specific)
spec.configure(vector_encoders={
    "openai_small": embed_openai_small,
    "openai_large": embed_openai_large,
})

# 2. Per-model override
spec.add_model(Doc, vector_encoders={"summary": "openai_large"})  # or a callable

# 3. Per-field override (most specific)
Vector(dim=1536, encoder="openai_small")
```

---

## 3. Querying

### Python SDK (QB)

```python
from specstar.query import QB

q = (
    (QB["embedding"].cosine(query_vec) < 0.3)
    .sort(QB["embedding"].cosine(query_vec))
    .limit(10)
    .build()
)
mgr.list_resources(q, returns=["data"])
```

`Field.cosine(q)`, `Field.l2(q)`, `Field.ip(q)` build a vector-distance expression.
- Use `< / <= / > / >=` to make a **filter** (threshold).
- Pass it to `.sort(...)` to make a **sort** (ascending = nearest first).
- `.desc()` for descending.

Vector conditions compose with scalar conditions via `&` / `|` / `~`:

```python
((QB["doctype"] == "abc") & (QB["embedding"].cosine(q) < 0.3))
    .sort(QB["embedding"].cosine(q))
```

### REST

Use the query-builder (`qb`) param on the search route — the same `QB[...]`
expression you'd write in Python, URL-encoded. `cosine`, `l2` and `ip` are
supported:

```http
GET /docs/data?qb=QB['embedding'].cosine('how to use vectors') < 0.3
```

Add a vector ranking with `.sort(...)`. A scalar/threshold filter must lead so
the expression is a full query rather than a bare distance (use a loose
threshold like `< 2.0` — cosine distance maxes at 2.0 — if you only want ranking):

```http
GET /docs/data?qb=(QB['embedding'].cosine('how to use vectors') < 2.0).sort(QB['embedding'].cosine('how to use vectors')).limit(10)
```

`query_vector` can be either:
- a `list[float]` (the vector itself), or
- a `str` — the framework calls the field's registered encoder before dispatching.

The string form keeps URLs short and lets you debug from `curl`. Pass a
raw 1536-dim vector via the URL only if you accept the URL-length tradeoff.
Combine clauses with `&`/`|` as usual, but URL-encode them (`%26`/`%7C`) so
they aren't parsed as query-string separators.

> **Not yet supported:** the raw `conditions=[...]` / `sorts=[...]` JSON params
> do not accept `VectorDistanceCondition` / `VectorDistanceSort` — use the `qb`
> form above for vector search over REST.

---

## 4. Choosing a distance metric

| Metric | When | pgvector op |
|---|---|---|
| `"cosine"` | Sentence / document embeddings (OpenAI, Cohere, BGE …). **Default** if none specified. | `<=>` |
| `"l2"` | Image / signal vectors. Euclidean. | `<->` |
| `"ip"` | Pre-normalized vectors where you want raw dot product. | `<#>` |

Resolution order: annotation `Vector(distance=...)` → per-call (`QB["e"].l2(q)`)
→ default `"cosine"`. If the per-call distance differs from the annotation's
distance, the per-call value wins.

---

## 5. Backend matrix

| Backend | Behavior |
|---|---|
| `postgres` + pgvector | Native `vector(N)` column + HNSW index + SQL operators. |
| `postgres` without pgvector | `add_model` for a Vector field raises — install the extension or switch backend. |
| `memory`, `disk`, `sqlite3`, `redis`, `df`, `sqlalchemy`, `fast_slow` | Brute-force Python comparison (O(n)). Suitable for dev / tests. |

The capability is exposed via `IMetaStore.supports_native_vector_search`.

---

## 6. Dimensions above the HNSW limit

pgvector's HNSW index supports up to 2 000 dimensions. SpecStar handles larger
embeddings (e.g. OpenAI `text-embedding-3-large` at 3 072) by:

- Storing the **full** vector in the resource payload (via `IResourceStore`).
- Indexing only the **first 2 000 dimensions** in the pgvector column.

This works well for Matryoshka-trained embeddings, where the truncated prefix
is itself a meaningful (lower-resolution) embedding. A startup warning is
logged so non-Matryoshka users notice.

---

## 7. Backfilling existing data

When you add a `Vector` field to a model that already has rows, the new
column starts as `NULL`. Run the bundled CLI to populate it:

```bash
specstar backfill-vectors --spec myapp:spec --model doc --field summary
```

`--spec` is a `module:attr` reference to your `SpecStar` instance.
`--model` is the **registered resource name** (the same string you'd pass
to `spec.get_resource_manager("doc")`). With the default `kebab`
naming, `class Doc` registers as `"doc"`; `class MyDoc` registers as
`"my-doc"`. If you set `name=` explicitly on `add_model`, use that value.

This works only for **`Embedding`** fields (the source `content` is the input
to the encoder). For raw `list[float] + Vector` fields, you must supply the
vectors yourself via `update()` because the framework has no way to recompute
them.

---

## 8. Validation

A `VectorDimValidator` is auto-mounted by `add_model`. On `create` / `update`
/ `modify`, any vector whose length doesn't match the annotated `dim` raises
`ValidationError`:

```
ValidationError: Vector field 'embedding': expected dim=1536, got 512
```

If you pass an `Embedding` without a vector (i.e. `Embedding(content="...")`),
the validator skips it — the processor will fill it in.

---

## 9. Cache reuse on update

The processor only calls the encoder when **content** or **encoder_id** has
changed. Updating a doc's `title` (with the same `summary.content`) is free —
no extra API call.

If you switch encoders (e.g. `openai_small` → `openai_large`), all rows are
re-encoded on next write or via `backfill-vectors`.

---

## 10. OpenAPI

Vector field properties carry custom extensions for downstream tools and admin
UIs:

```json
{
  "summary": {
    "type": "object",
    "x-vector-dim": 1536,
    "x-vector-distance": "cosine",
    "x-vector-encoder-id": "openai_small"
  }
}
```

---

## See also

- [Vector & Embedding — concepts](../concepts/vector-and-embedding.md)
- [Query Builder](query-builder.md)
- [Binary Data](binary-data.md)
