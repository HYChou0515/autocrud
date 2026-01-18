---
title: Example Collection
description: Various usage examples of AutoCRUD
---

# Example Collection

This section collects various AutoCRUD usage examples, from basic to advanced applications.

## Quick Navigation

<div class="grid cards" markdown>

-   :material-rocket-launch:{ .lg .middle } __Basic CRUD__

    ---

    Learn the basic create, read, update, and delete operations

    [:octicons-arrow-right-24: Basic Examples](basic-crud.md)

-   :material-shield-lock:{ .lg .middle } __Permission Control__

    ---

    Implement permission systems such as RBAC and ACL

    [:octicons-arrow-right-24: Permission Examples](permissions.md)

-   :material-history:{ .lg .middle } __Version Control__

    ---

    Revision history, drafts, and switching revisions

    [:octicons-arrow-right-24: Versioning Examples](versioning.md)

-   :material-magnify:{ .lg .middle } __Search & Filtering__

    ---

    Complex queries, indexing, and pagination

    [:octicons-arrow-right-24: Search Examples](search.md)

</div>

## Real-world Application Examples

### CMS Content Management System

A complete blog article management system, including:

- Article version control
- Draft/publish workflow
- Categories and tags
- Image uploads

[:octicons-arrow-right-24: View Example](cms-example.md)

### E-commerce Order System

An order management system demonstrating:

- Complex data relationships
- State machine management
- Audit logs
- Hierarchical permissions

[:octicons-arrow-right-24: View Example](ecommerce-example.md)

### IoT Device Management

IoT device data collection and management:

- Time-series data
- High-throughput write optimization
- Real-time queries
- Alerting system

[:octicons-arrow-right-24: View Example](iot-example.md)

## Code Snippets

### Quick Start Template

The simplest AutoCRUD application:

```python
from fastapi import FastAPI
from autocrud import AutoCRUD
from msgspec import Struct

class Item(Struct):
    name: str
    price: float

crud = AutoCRUD()
crud.add_model(Item)

app = FastAPI()
crud.apply(app)
```

### Model with Indexes

Supports search and filtering:

```python
crud.add_model(
    Item,
    indexed_fields=[
        ("price", float),
        ("category", str),
    ]
)
```

### Custom Permissions

```python
from autocrud.permission import RBACPermissionChecker

permission_checker = RBACPermissionChecker({
    "admin": {"read", "create", "update", "delete"},
    "editor": {"read", "create", "update"},
    "viewer": {"read"}
})

crud = AutoCRUD(permission_checker=permission_checker)
```

### Event Handling

```python
from autocrud.types import IEventHandler, EventContext

class LoggingHandler(IEventHandler):
    def after_create(self, ctx: EventContext, resource):
        print(f"Created: {resource.resource_id}")
    
    def after_update(self, ctx: EventContext, resource):
        print(f"Updated: {resource.resource_id}")

crud = AutoCRUD(event_handlers=[LoggingHandler()])
```

## Project Examples Repository

View the complete project examples:

- [GitHub - autocrud/examples](https://github.com/HYChou0515/autocrud/tree/master/examples)

## Advanced Examples

- [GraphQL Integration](../advanced/graphql.md#examples)
- [Custom Storage](../advanced/custom-storage.md#examples)
- [Message Queue](../advanced/message-queue.md#examples)
- [Performance Optimization](../advanced/performance.md#best-practices)
