# Core Concepts

This page introduces the fundamental concepts used by AutoCRUD.

AutoCRUD is built around a **versioned resource model** where each resource
maintains a revision history and metadata.

---

# Resource

A **Resource** is the logical entity stored in the system.

Examples:

- User
- Order
- Document
- Image

Each resource has a stable identifier:

```

resource_id

```

Example:

```

user_123
order_456

```

The resource ID does **not change across revisions**.

---

# Revision

A **Revision** represents a specific version of a resource.

Each revision has:

```

revision_id
parent_revision_id
status
created_time
created_by

```

### Immutable mode (default)

Using `update` or `patch` creates a new revision.

```

revision1 -> revision2 -> revision3

```

### Draft mode (`modify`)

`modify` updates the current revision **in-place**.

This mode is intended for draft editing workflows.

---

# Resource Metadata

Metadata is stored separately from resource data.

Example fields:

```

resource_id
current_revision_id
created_time
updated_time
created_by
updated_by
schema_version
is_deleted

```

Metadata is accessed via:

```

GET /{model}/{resource_id}?returns=meta

```

---

# Resource Data

The **data** section contains the actual resource payload defined by the schema.

Example:

```

class User(msgspec.Struct):
name: str
email: str
age: int

```

This section is returned via:

```

GET /{model}/{resource_id}?returns=data

```

---

# Revision Info

Revision info describes a specific version of a resource.

Example fields:

```

revision_id
parent_revision_id
status
schema_version

```

Accessed via:

```

GET /{model}/{resource_id}?returns=revision_info

```

---

# ResourceManager

`ResourceManager` is the core component responsible for managing resources.

Responsibilities:

- create resources
- update revisions
- validate data
- enforce constraints
- manage metadata
- perform queries

Example:

```python
rm = crud.add_model(User)
```

---

# Blob

AutoCRUD supports binary data through the `Binary` type.

Binary data is stored outside the main resource payload.

Example:

```python
class Image(msgspec.Struct):
file: Binary
```

Binary storage:

```

Binary(data=...)

-> stored in blob store
-> replaced with file_id

```

Retrieval:

```

GET /{model}/{resource_id}/blobs/{file_id}

```

---

# Query System

Resources can be queried using the **QB (Query Builder)** syntax.

Example:

```

qb=QB["age"].gt(18) & QB["status"].eq("active")

```

This is the **recommended query method**.
