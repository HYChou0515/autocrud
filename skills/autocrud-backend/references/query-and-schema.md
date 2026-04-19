# Query Builder & Schema — Detailed Reference

## Query Builder (QB)

The `QB` class provides a Django-like API for building resource queries. Queries are parsed safely via AST — no `eval()`.

```python
from autocrud.query import QB
```

### Field Access

```python
QB["field_name"]          # bracket notation (recommended)
QB["user.email"]          # nested fields via dot path
QB["class"]               # reserved words safe
```

### Comparison Operators

All return query condition objects that can be combined with `&`, `|`, `~`.

| Method | Operator | Example |
|--------|----------|---------|
| `.eq(value)` | `==` | `QB["name"].eq("Alice")` or `QB["name"] == "Alice"` |
| `.ne(value)` | `!=` | `QB["name"].ne("Bob")` or `QB["name"] != "Bob"` |
| `.gt(value)` | `>` | `QB["age"].gt(18)` or `QB["age"] > 18` |
| `.gte(value)` | `>=` | `QB["age"].gte(18)` or `QB["age"] >= 18` |
| `.lt(value)` | `<` | `QB["age"].lt(18)` or `QB["age"] < 18` |
| `.lte(value)` | `<=` | `QB["age"].lte(18)` or `QB["age"] <= 18` |
| `.contains(s)` | string contains | `QB["email"].contains("@gmail")` |
| `.startswith(s)` | string prefix | `QB["name"].startswith("A")` |
| `.endswith(s)` | string suffix | `QB["name"].endswith("son")` |
| `.in_(list)` | in collection | `QB["role"].in_(["admin", "user"])` |
| `.is_null()` | is None | `QB["bio"].is_null()` |
| `.is_not_null()` | is not None | `QB["bio"].is_not_null()` |
| `.between(lo, hi)` | range inclusive | `QB["level"].between(20, 80)` |

### Logical Operators

```python
# AND
q = (QB["age"].gte(18) & QB["role"].eq("admin"))
q = QB.all(QB["age"].gte(18), QB["role"].eq("admin"), QB["active"].eq(True))

# OR
q = (QB["role"].eq("admin") | QB["role"].eq("mod"))
q = QB.any(QB["role"].eq("admin"), QB["role"].eq("mod"))

# NOT
q = ~QB["name"].eq("Bob")

# Match all (no filter)
q = QB.all()
```

### Chaining Methods

```python
q = QB["level"].gte(50)
    .filter(QB["name"].contains("A"))   # add AND condition
    .exclude(QB["role"].eq("banned"))    # add NOT condition
    .sort("-level")                       # sorting
    .limit(10)                            # max results
    .offset(20)                           # skip N results
```

### Sorting

```python
# String-based (prefix - = descending, + = ascending)
q = QB["level"].gte(1).sort("-level")              # level descending
q = QB["level"].gte(1).sort("-level", "+name")     # multi-sort
q = QB["level"].gte(1).sort("-created_at")         # by meta fields

# Method-based
q = QB["level"].gte(1).sort(QB["gold"].desc())
q = QB["level"].gte(1).sort(QB["name"].asc())
```

### Pagination

```python
q = QB["level"].gte(1).limit(10)            # max 10 results
q = QB["level"].gte(1).limit(10).offset(20) # skip first 20
q = QB["level"].gte(1).page(2, 10)          # page 2, 10 per page
q = QB["level"].gte(1).first()              # shorthand for limit(1)
```

### Metadata Field Queries

Built-in accessors for `ResourceMeta` fields:

| Accessor | Type | Example |
|----------|------|---------|
| `QB.resource_id()` | str | `QB.resource_id().eq("abc-123")` |
| `QB.revision_id()` | str | `QB.revision_id().contains("abc")` |
| `QB.created_time()` | datetime | `QB.created_time().gte(dt.datetime(2024, 1, 1))` |
| `QB.updated_time()` | datetime | `QB.updated_time().lte(dt.datetime.now())` |
| `QB.created_by()` | str | `QB.created_by().eq("admin")` |
| `QB.updated_by()` | str | `QB.updated_by().ne("guest")` |
| `QB.is_deleted()` | bool | `QB.is_deleted().eq(False)` |
| `QB.schema_version()` | str | `QB.schema_version().eq("v2")` |
| `QB.total_revision_count()` | int | `QB.total_revision_count().gte(5)` |

### HTTP API Usage

Queries can be passed as query parameters in HTTP requests:

```
GET /user?qb=QB["age"] > 18
GET /user?qb=(QB["age"] > 18) & (QB["status"] == "active")
GET /user?qb=QB.created_by().eq("admin")
GET /user?qb=QB.created_time() >= datetime(2024,1,1)
```

> When `qb` parameter is provided, it cannot be combined with `data_conditions`, `conditions`, or `sorts` parameters.

### Complete Examples

```python
rm = crud.get_resource_manager(Character)

# 1. High-level characters
metas = rm.search_resources(QB["level"].gte(50).limit(10))

# 2. Complex multi-condition
metas = rm.search_resources(
    (QB["level"].between(20, 80) & QB["guild_name"].is_not_null()).limit(5)
)

# 3. OR query
metas = rm.search_resources(
    (QB["level"].gte(80) | QB["gold"].gte(500000)).limit(5)
)

# 4. Sorted top 3
metas = rm.search_resources(
    QB["level"].gte(1).sort("-level").limit(3)
)

# 5. String contains
metas = rm.search_resources(
    QB["name"].contains("Hero").limit(5)
)

# 6. IN query
metas = rm.search_resources(
    QB["guild_name"].in_(["Alliance", "Horde"]).limit(10)
)

# 7. Recent metadata-based query
metas = rm.search_resources(
    QB.created_time()
    .gte(dt.datetime.now() - dt.timedelta(hours=1))
    .sort(QB.created_time().desc())
    .limit(3)
)

# 8. Exclude specific groups
metas = rm.search_resources(
    QB["level"].gte(1)
    .exclude(QB["guild_name"].eq("Beginner Town"))
    .sort("-level")
    .limit(5)
)
```

---

## Schema & Migration — Detailed Reference

### Schema Class

```python
from autocrud import Schema

schema = Schema(
    model: type[T],        # target Struct class
    version: str,          # schema version identifier (e.g., "v1", "v2")
    validator: Callable | IValidator | None = None,  # validation function or class
)
```

### Migration Steps

```python
# IO-based migration (default): receives raw bytes stream
def migrate_v1_to_v2(raw: IO[bytes]) -> dict:
    import msgspec
    old = msgspec.json.decode(raw.read())
    return {"full_name": old["first_name"] + " " + old["last_name"]}

Schema(UserV2, "v2").step("v1", migrate_v1_to_v2)

# Typed migration (recommended): auto-decodes source to Struct
def migrate_v1_to_v2(old: UserV1) -> UserV2:
    return UserV2(full_name=f"{old.first_name} {old.last_name}")

Schema(UserV2, "v2").step("v1", migrate_v1_to_v2, source_type=UserV1)
```

### Chained Migrations

```python
# v1 → v2 → v3 (sequential)
Schema(UserV3, "v3").step("v1", fn_v1_to_v2).step("v2", fn_v2_to_v3)

# Multiple paths (BFS finds shortest at runtime)
schema = (
    Schema(UserV3, "v3")
    .step("v1", fn_v1_to_v2)      # v1 → v2
    .step("v2", fn_v2_to_v3)      # v2 → v3
    .plus("v1", fn_v1_to_v3)      # v1 → v3 directly (shortcut)
)
# BFS will pick v1→v3 (1 step) over v1→v2→v3 (2 steps)
```

### Validators

Validators run on every `create()` and `update()`:

```python
# Function-based
def validate_user(user: User) -> None:
    if user.age < 0:
        raise ValueError("Age must be non-negative")
    if not user.email:
        raise ValueError("Email required")

Schema(User, "v1", validator=validate_user)

# Class-based (IValidator protocol)
class SkillValidator:
    def validate(self, data: Skill) -> None:
        if data.required_level < 0:
            raise ValueError("Level must be non-negative")

Schema(Skill, "v1", validator=SkillValidator())
```

### Runtime Migration

```python
rm = crud.get_resource_manager(User)

# Migrate current revision to latest schema
rm.migrate(resource_id)

# Migrate a specific old revision
rm.migrate(resource_id, revision_id="abc-123:1")

# Switching to unmigrated revision raises error
from autocrud import RevisionNotMigratedError
try:
    rm.switch(resource_id, old_revision_id)
except RevisionNotMigratedError:
    rm.migrate(resource_id, revision_id=old_revision_id)
    rm.switch(resource_id, old_revision_id)
```

### Schema Version Lifecycle

1. **Create**: Revision stored with current `schema_version`
2. **Update**: New revision uses current `schema_version`
3. **Read old revision**: AutoCRUD attempts to decode with current schema
4. **Migration**: Converts old revision data to current schema format
5. **Switch**: Requires target revision to be at current schema_version

### Encoding Options

```python
# Set encoding globally
crud.configure(encoding="json")      # human-readable, larger
crud.configure(encoding="msgpack")   # binary, compact, faster

# Per-model encoding
crud.add_model(User, encoding="msgpack")
```
