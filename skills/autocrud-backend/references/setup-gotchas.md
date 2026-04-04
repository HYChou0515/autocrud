# Before You Write Code — Common Gotchas

These are the most frequent mistakes when setting up AutoCRUD. Internalizing them saves significant debugging time.

## 1. `indexed_fields`, NOT `indexes` or `index_fields`
The parameter for `crud.add_model()` is **`indexed_fields`** — not `indexes`, not `index_fields`, not `index`. This is the most common parameter name mistake.
```python
# ✓ CORRECT
crud.add_model(User, indexed_fields=[("email", str)])
# ❌ WRONG — these parameter names don't exist
crud.add_model(User, indexes=[...])
crud.add_model(User, index_fields=[...])
```

## 2. Ref names must match the **resource name**, not the Python class name
With default kebab naming (`model_naming="kebab"`), class `BlogPost` becomes resource name `blog-post`. Ref annotations must use the **resource name** (kebab-case), not the Python class name or snake_case:
```python
class BlogPost(Struct):
    title: str

class Comment(Struct):
    # ✓ CORRECT — matches the resource name (kebab-case, because BlogPost → blog-post)
    post: Annotated[str, Ref("blog-post")]
    # ❌ WRONG — "blog_post" is snake_case, but the resource name is "blog-post"
    # post: Annotated[str, Ref("blog_post")]
    # ❌ WRONG — "BlogPost" is the Python class name, not the resource name
    # post: Annotated[str, Ref("BlogPost")]
```

The naming conversion table (default `model_naming="kebab"`):

| Python Class | Resource Name | Ref Value |
|-------------|--------------|-----------|
| `User` | `user` | `Ref("user")` |
| `BlogPost` | `blog-post` | `Ref("blog-post")` |
| `GameEvent` | `game-event` | `Ref("game-event")` |

## 3. `autocrud.annotations` does NOT exist
All annotations (`Unique`, `Ref`, `DisplayName`, `OnDelete`, etc.) are imported directly from `autocrud`:
```python
# ✓ CORRECT
from autocrud import Unique, Ref, DisplayName, OnDelete
# ❌ WRONG — this module doesn't exist
# from autocrud.annotations import Unique
```

## 4. Storage factories are NOT in `autocrud` top-level
Storage factories must be imported from `autocrud.resource_manager.storage_factory`:
```python
# ✓ CORRECT
from autocrud.resource_manager.storage_factory import DiskStorageFactory
from autocrud.resource_manager.storage_factory import MemoryStorageFactory
from autocrud.resource_manager.storage_factory import S3StorageFactory
from autocrud.resource_manager.storage_factory import PostgresStorageFactory
# ❌ WRONG — not exported at top level
# from autocrud import DiskStorageFactory
```

## 5. Model registration order matters for Ref validation
If `Comment` has `Ref("blog-post")`, register `BlogPost` first (or at least before `crud.apply()`). AutoCRUD validates refs at `apply()` time, but warnings appear during `add_model()` if the target isn't registered yet. Best practice: register models in dependency order (parents before children).

## 6. `uvicorn` is not a dependency of autocrud
You need to install it separately:
```bash
uv add uvicorn   # or: pip install uvicorn
```
