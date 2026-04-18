# Core Concepts

This page goes one step deeper than the overview page.

It explains how the main AutoCRUD building blocks behave in practice and why that behavior matters when you build real applications.

---

## 1. Resource vs. revision

A resource is the long-lived logical entity, such as a user, document, job, or configuration object.

A revision is one version of that resource at a point in time.

This distinction matters because the resource ID stays stable while the actual content can evolve through multiple revisions.

---

## 2. Immutable history vs. draft editing

By default, write operations such as `update` and `patch` create a new revision.

That gives you a revision trail like this:

```text
revision1 -> revision2 -> revision3
```

When you use `modify`, AutoCRUD updates the current draft in place instead.

Use the default immutable path when you care about history and auditing. Use draft-style modification only when that editing model is truly needed.

---

## 3. Metadata is a first-class layer

AutoCRUD keeps metadata separate from the resource payload.

That metadata includes things like:

- the current revision pointer
- creation and update timestamps
- schema version
- deletion status
- indexed values used for search

This separation is what makes search, lifecycle handling, and operational tooling much easier to keep consistent.

---

## 4. The ResourceManager is the enforcement layer

The ResourceManager is not just a helper object. It is the place where the framework coordinates:

- validation
- revision creation
- metadata updates
- constraints
- event handlers
- permission checks
- storage access

That is why most behavior in AutoCRUD becomes predictable once you understand how the manager mediates operations.

---

## 5. Binary data is handled outside the main payload

When a model includes `Binary`, the file bytes are stored in the blob backend while the resource keeps the associated metadata such as file ID and size.

This keeps normal resource payloads manageable while still supporting file-heavy workflows.

See also:

- [Binary data](/autocrud/howto/binary-data)

---

## 6. Querying depends on indexed fields

AutoCRUD search is built around indexed metadata rather than full-payload scans.

That is an important design choice:

- it makes search behavior more predictable
- it improves operational performance
- it encourages you to think about searchable fields up front

See also:

- [Query system](/autocrud/concepts/query-system)
- [Query builder](/autocrud/howto/query-builder)

---

## 7. Why these concepts matter together

The core concepts are most useful when you see them as one system:

- resources provide identity
- revisions provide history
- metadata provides indexable operational state
- ResourceManager enforces the lifecycle rules

That combination is what allows AutoCRUD to generate practical APIs while keeping behavior consistent across different storage and integration patterns.
