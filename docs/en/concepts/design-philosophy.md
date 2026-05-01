# Design philosophy

This page explains the **principles and trade-offs** behind SpecStar.

If [Why SpecStar exists](/specstar/concepts/why-specstar) explains the problem, this page explains the design choices used to solve it.

---

## 1. Generate infrastructure from the model

The first principle is that developers should define the domain model once and avoid rebuilding the same supporting infrastructure repeatedly.

From that model, SpecStar can derive:

- API routes
- validation flow
- storage coordination
- indexing and search behavior
- revision history

The goal is not to remove application logic. The goal is to remove repetitive framework glue.

---

## 2. Treat history as a first-class concern

Many CRUD systems treat updates as destructive overwrites.

SpecStar instead assumes that revision history is often operationally useful:

- for auditing
- for rollback
- for draft workflows
- for debugging and recovery

That is why versioned resources are central to the design rather than an optional add-on.

---

## 3. Separate payload data from operational metadata

SpecStar keeps the resource payload separate from metadata such as revision pointers, timestamps, deletion state, and indexed values.

This makes it easier to support:

- consistent lifecycle handling
- predictable search behavior
- faster operational queries
- flexible storage strategies

---

## 4. Centralize lifecycle rules in the ResourceManager

A second core principle is that validation, permissions, revision creation, and event hooks should pass through one enforcement layer.

That layer is the ResourceManager.

This helps keep behavior consistent across different routes and storage backends instead of scattering the rules across controllers, helpers, and direct storage calls.

---

## 5. Stay flexible about storage

SpecStar is designed to be API- and model-oriented rather than tied to a single database engine.

That is why metadata, revisions, and blobs can be backed by different storage layers depending on the deployment needs.

This allows the same conceptual model to work in:

- local development
- single-node deployments
- cloud or object-storage-heavy setups

---

## 6. Prefer practical automation over framework sprawl

SpecStar is intentionally opinionated around a specific class of applications:

- API-centric systems
- operational tools
- version-aware admin or content workflows
- services that benefit from generated CRUD plus custom business logic

It is not trying to be a universal replacement for every web framework pattern.

---

## The trade-off

This design gives you strong consistency and less repetitive code, but it also means SpecStar is most valuable when your project fits a **spec-driven, API-first** workflow.

If your team wants a traditional full-stack monolith or a purely database-first GraphQL layer, another tool may be a better fit.

### When SpecStar is usually the better fit

SpecStar is especially effective for applications such as:

- internal admin and operations tools
- configuration or content management systems
- resource-heavy business APIs that need audit history
- job and workflow backends where task state should be tracked like normal resources
- FastAPI services that benefit from generated CRUD plus custom business logic

Typical signals that SpecStar fits well:

- you want revision history and restore behavior by default
- your team prefers Python models as the source of truth
- you want API-first development rather than server-rendered pages
- you may want an auto-generated admin UI later

### When Django is usually the better fit

Django is often a better choice for:

- traditional business applications with server-rendered pages
- form-heavy back-office systems that rely on the Django admin and ORM
- teams already standardized on Django conventions and reusable apps
- projects where the full-stack monolith is a feature, not a limitation

Typical signals that Django fits well:

- templates, forms, session-based auth, and admin are central to the product
- your team wants a mature batteries-included web framework
- the project is not primarily API-first

### When other approaches may fit better

A database-first GraphQL solution such as Hasura is often a better fit when:

- PostgreSQL is already the main source of truth
- frontend teams want GraphQL quickly
- most of the complexity is in relational querying rather than Python-side lifecycle logic

A more custom FastAPI setup may be better when:

- the service is small and highly specialized
- the domain is not CRUD-oriented
- you need very custom request handling, protocols, or orchestration that gains little from generation

In short, SpecStar works best when the problem looks like **versioned resources + repeatable APIs + operational tooling**.

---

## Read next

- [Architecture](/specstar/concepts/architecture) — how these principles appear in the system design
- [Resource lifecycle](/specstar/concepts/resource-lifecycle) — how the revision model behaves in practice
- [SpecStar vs Hasura vs Django](/specstar/concepts/specstar-vs-hasura-vs-django) — when SpecStar is the better fit
