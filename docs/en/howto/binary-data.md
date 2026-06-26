# Binary Data

SpecStar supports binary or blob workflows for files such as images, documents, and other uploaded content.

The key type is `Binary`, which lets you store file metadata in the resource while keeping the raw bytes in the blob store.

---

## 1. Add a binary field to your model

```python
from msgspec import Struct

from specstar.types import Binary


class Avatar(Struct):
    title: str
    image: Binary | None = None
```

When a resource contains binary data, SpecStar can move the raw bytes into the configured blob backend and keep only the file metadata in the stored resource.

---

## 2. Enable blob routes

Add the blob route template before applying the app:

```python
from fastapi import FastAPI

from specstar import spec
from specstar.crud.route_templates.blob import BlobRouteTemplate

app = FastAPI()

spec.add_model(Avatar)
spec.add_route_template(BlobRouteTemplate())
spec.apply(app)
```

This exposes the global blob endpoints.

---

## 3. Upload a file directly

For a one-shot upload, use the multipart endpoint:

- `POST /blobs/upload`

The response contains binary metadata such as:

- `file_id`
- `size`
- `content_type`

You can then reference that file in your normal create or update payload.

Example JSON payload after upload:

```json
{
  "title": "team logo",
  "image": {
    "file_id": "abc123"
  }
}
```

---

## 4. Use upload sessions for larger files

SpecStar also provides an upload-session flow for larger or multi-part uploads.

| Step | Method | Endpoint |
| --- | --- | --- |
| create session | POST | `/blobs/upload-sessions` |
| inspect session | GET | `/blobs/upload-sessions/{upload_id}` |
| send content | PUT | `/blobs/upload-sessions/{upload_id}/content` |
| finalize | POST | `/blobs/upload-sessions/{upload_id}/finalize` |
| abort | POST | `/blobs/upload-sessions/{upload_id}/abort` |

The upload session reports whether the client should use:

- `proxy` mode, where bytes are sent through the SpecStar endpoint
- `single_put` mode, where the blob store provides a direct upload URL

This is especially useful for S3-style storage backends.

---

## 5. Download binary content

To retrieve stored bytes, use:

- `GET /blobs/{file_id}`

Depending on the backend, SpecStar may:

- stream the file
- redirect to a signed URL
- return the bytes directly

---

## 6. Blob lifecycle and garbage collection

Blobs are **content-addressed and deduplicated**: identical bytes always map to the
same `file_id`, so a single blob can be shared by many revisions, many resources, and
even many models that share the same blob store.

Because of that sharing, SpecStar never deletes a blob the moment a resource goes away.
Even `permanently_delete` only removes the resource's metadata and revisions — the blob
itself may still be referenced elsewhere. Reclaiming truly-unreferenced blobs is done by
explicit garbage-collection passes that you run (or schedule) yourself:

```python
# Cheap, scan-free pass: quarantine blobs that just lost their last reference.
spec.gc(mode="incremental")

# Authoritative pass: rescans every model's revisions, then permanently removes
# blobs that no live revision references. This is the only pass that deletes.
spec.gc(mode="reconcile")

# Tune the two grace periods (defaults shown).
spec.gc(mode="reconcile", t1="1h", t2="24h")
```

The two passes work together:

- **`incremental`** is cheap and never rescans revision data. When `permanently_delete`
  drops a blob's last reference, that blob becomes a candidate; after the `t1` grace the
  incremental pass *moves it to a quarantine area* — a reversible step, not a delete. It
  never deletes.
- **`reconcile`** is authoritative. It rescans the revisions of **all** models, computes
  the exact set of still-referenced blobs, **restores** any blob that is still referenced
  (self-healing), **quarantines** any newly orphaned blob older than `t1`, and
  **permanently deletes** quarantined blobs that no revision references and that have sat in
  quarantine past `t2`. It also brings pre-existing blobs under management on its first run,
  so **no migration is needed**.

A typical schedule runs `incremental` often (e.g. hourly) and `reconcile` occasionally
(e.g. nightly). SpecStar does **not** spawn a background thread for you — wire `gc()` into
your own scheduler/cron.

Safety: a blob is never deleted while any revision still references it (including
soft-deleted resources, whose revisions are retained). A blob is only removed after it has
sat unreferenced in quarantine past `t2`, confirmed by a scan that is authoritative across
every model that shares the blob store. While a blob sits in quarantine it remains fully
readable, and if it is referenced again it is restored out of quarantine immediately.

> **Caveats**
>
> - GC only manages content-addressed blobs that are referenced through a resource's
>   `Binary` fields. Blobs you `put` with an explicit `key` and reference out-of-band are
>   not tracked and may be collected.
> - A blob store must be owned by a single SpecStar app. Sharing one bucket/prefix across
>   independent apps breaks GC's view of what is referenced.

---

## What the Binary type stores

A `Binary` value typically contains:

- `file_id`
- `size`
- `content_type`
- optional raw `data` during input time

In most stored resources, the raw byte content is not kept inline.

---

## Good practices

- prefer upload sessions for large files
- keep blob storage configured explicitly in production systems
- store only the metadata you need in the resource itself
- use content types when available so downloads are served correctly
- combine blob support with S3-compatible storage for multi-node deployments
- schedule `gc()` (incremental often, reconcile occasionally) so unreferenced blobs are reclaimed

---

## Related pages

- [API conventions](/specstar/howto/api-conventions)
- [Routes generation](/specstar/howto/routes)
- [Prune old revisions](/specstar/howto/prune-revisions) — decrefs blobs for GC to reclaim
- [From demo to production](/specstar/guides/from-demo-to-production)
- [Examples](/specstar/examples/)
