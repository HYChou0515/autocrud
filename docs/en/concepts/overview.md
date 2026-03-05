# Overview

AutoCRUD is a **model-driven backend framework for FastAPI** that manages application data as **versioned resources**.

Instead of manually implementing CRUD APIs, validation, search, and storage logic, AutoCRUD generates these capabilities automatically from your resource models.

---

# The core idea

AutoCRUD manages data using three fundamental concepts:

- **Resource**
- **Revision**
- **ResourceManager**

Together they form the foundation of the framework.

---

# Resource

A **resource** represents a logical entity in your application.

Examples:

- `User`
- `Article`
- `Job`
- `Configuration`

Resources are defined as Python data models.

```python
class User(Struct):
    name: str
    email: str
```

Each resource has a unique identifier (`resource_id`) and associated metadata.

---

# Revision

AutoCRUD stores data as **immutable revisions**.

Instead of overwriting data, updates create new revisions.

```
Resource
 ├── r1
 ├── r2
 └── r3
```

The currently active revision is tracked by metadata:

```
ResourceMeta.current_revision_id
```

This enables built-in support for:

* audit history
* rollback
* draft workflows
* debugging

---

# ResourceManager

All operations on resources go through the **ResourceManager**.

Example:

```python
resource_manager.create(data)
resource_manager.get(resource_id)
resource_manager.update(resource_id, new_data)
```

The manager coordinates:

* validation
* revision creation
* metadata updates
* storage operations
* event handlers

Developers do not interact directly with storage systems.

---

# Schema and validation

Resources may define schemas that control validation and constraints.

Examples include:

* field validation
* uniqueness constraints
* custom validation hooks

These checks run automatically when resources are created or updated.

---

# References

Resources and revisions can be referenced using:

* `Ref` – reference to a resource
* `RefRevision` – reference to a specific revision

These types allow relationships between resources while preserving revision history.

---

# Summary

AutoCRUD is built around a simple mental model:

```
ResourceManager
    ↓
Resource
    ↓
Revisions
```

By combining versioned resources, metadata indexing, and storage abstraction, AutoCRUD provides a consistent way to build APIs without writing repetitive infrastructure code.
