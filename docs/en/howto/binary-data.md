# Binary Data

AutoCRUD supports binary or blob workflows for files such as images, documents, and other uploaded content.

The key type is `Binary`, which lets you store file metadata in the resource while keeping the raw bytes in the blob store.

---

## 1. Add a binary field to your model

```python
from msgspec import Struct

from autocrud.types import Binary


class Avatar(Struct):
    title: str
    image: Binary | None = None
```

When a resource contains binary data, AutoCRUD can move the raw bytes into the configured blob backend and keep only the file metadata in the stored resource.

---

## 2. Enable blob routes

Add the blob route template before applying the app:

```python
from fastapi import FastAPI

from autocrud import crud
from autocrud.crud.route_templates.blob import BlobRouteTemplate

app = FastAPI()

crud.add_model(Avatar)
crud.add_route_template(BlobRouteTemplate())
crud.apply(app)
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

AutoCRUD also provides an upload-session flow for larger or multi-part uploads.

| Step | Method | Endpoint |
| --- | --- | --- |
| create session | POST | `/blobs/upload-sessions` |
| inspect session | GET | `/blobs/upload-sessions/{upload_id}` |
| send content | PUT | `/blobs/upload-sessions/{upload_id}/content` |
| finalize | POST | `/blobs/upload-sessions/{upload_id}/finalize` |
| abort | POST | `/blobs/upload-sessions/{upload_id}/abort` |

The upload session reports whether the client should use:

- `proxy` mode, where bytes are sent through the AutoCRUD endpoint
- `single_put` mode, where the blob store provides a direct upload URL

This is especially useful for S3-style storage backends.

---

## 5. Download binary content

To retrieve stored bytes, use:

- `GET /blobs/{file_id}`

Depending on the backend, AutoCRUD may:

- stream the file
- redirect to a signed URL
- return the bytes directly

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

---

## Related pages

- [API conventions](/autocrud/howto/api-conventions)
- [Routes generation](/autocrud/howto/routes)
- [From demo to production](/autocrud/guides/from-demo-to-production)
- [Examples](/autocrud/examples/)
