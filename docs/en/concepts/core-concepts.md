# Core Concepts

This page defines the **core terms** used throughout the rest of the documentation.

If [Overview](/specstar/concepts/overview) gives you the map, this page gives you the vocabulary used throughout the docs.

---

## 1. Resource

A resource is the long-lived logical entity your application manages, such as a user, document, job, or configuration object.

A resource keeps the same identity even when its content changes.

---

## 2. Revision

A revision is one version of a resource at a specific point in time.

This distinction matters because the resource ID stays stable while the actual content evolves through multiple revisions.

By default, operations such as update and patch create a new revision rather than overwriting history.

---

## 3. Metadata

SpecStar keeps metadata separate from the main resource payload.

Metadata includes values such as:

- the current revision pointer
- creation and update timestamps
- schema version
- deletion status
- indexed values used for search

This separation makes lifecycle operations, search behavior, and operational tooling easier to keep consistent.

---

## 4. ResourceManager

The ResourceManager is the enforcement layer for resource behavior.

It coordinates:

- validation
- revision creation
- metadata updates
- constraints
- event handlers
- permission checks
- storage access

Once you understand the manager’s role, most SpecStar behavior becomes much easier to predict.

---

## 5. Schema version

A schema version tells SpecStar how a revision’s data shape relates to the current model definition.

This becomes important when your application evolves and you need migration paths between versions.

See also:

- [Schema](/specstar/concepts/schema)
- [Migrations](/specstar/howto/migrations)

---

## 6. Indexed search fields

SpecStar search is built around indexed metadata rather than full payload scans.

That design keeps search behavior more predictable and encourages you to identify important searchable fields explicitly.

See also:

- [Query system](/specstar/concepts/query-system)
- [Query builder](/specstar/howto/query-builder)

---

## Read next

- [Resource lifecycle](/specstar/concepts/resource-lifecycle) — how revisions change over time
- [Architecture](/specstar/concepts/architecture) — how the major components fit together
- [Binary data](/specstar/howto/binary-data) — how files are handled outside the main payload

