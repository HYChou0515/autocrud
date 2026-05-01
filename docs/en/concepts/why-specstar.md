# Why SpecStar exists

This page explains the **motivation** behind SpecStar.

If you want the system map, read [Overview](/specstar/concepts/overview). If you want precise terminology, read [Core concepts](/specstar/concepts/core-concepts).

---

## The recurring cost in API projects

Many FastAPI applications end up rebuilding the same operational layers around data:

- CRUD routes
- validation and input shaping
- pagination and filtering
- search and indexing
- permissions
- audit history
- background jobs
- internal admin tooling

These capabilities matter, but they are rarely the part of the product that makes it unique.

The problem is not that this work is unnecessary. The problem is that teams keep rewriting it from scratch.

---

## The spec-driven shift

SpecStar changes the development flow from:

$$
\text{build infrastructure first} \rightarrow \text{write domain logic later}
$$

to:

$$
\text{define the domain model} \rightarrow \text{generate the infrastructure around it}
$$

That shift is most useful when you want predictable APIs and operational behavior without spending most of the project on plumbing.

The name reflects this: you write the **spec** (a `msgspec.Struct`) and SpecStar generates the **rest of the star** — REST routes, GraphQL, search, version history, admin UI.

---

## Why versioning is built-in, not bolted on

Most CRUD generators stop at "model → API" — history-tracking is left to you. You'd add an audit log table, wire up event sourcing, or simply accept that "what was this row 3 weeks ago?" is a question you can't answer.

SpecStar treats every resource as a **versioned timeline** by default. Updates create new revisions; old revisions stay queryable; you can roll back, work in draft mode, or migrate forward through schema changes.

This is opt-in friendly. If you don't need history, you ignore it — the same routes work as plain CRUD. But when "who changed this and when?" becomes a real question, the answer is already there.

---

## Problems SpecStar is trying to reduce

SpecStar is a good fit when your project needs:

- repeatable CRUD APIs
- version-aware data handling
- consistent search behavior
- extension points for permissions and events
- optional job processing and admin workflows

It is especially useful for:

- internal tools
- administrative systems
- content and configuration management
- operational dashboards
- job-oriented backend services

---

## What it is not optimized for

SpecStar is not trying to replace every backend style.

It is not primarily:

- a full event-sourcing platform
- a general workflow engine
- a distributed data mesh
- a traditional server-rendered full-stack framework

Its value comes from making a common class of API-centric backend work simpler and more consistent.

---

## Read next

- [Overview](/specstar/concepts/overview) — the high-level system map
- [Core concepts](/specstar/concepts/core-concepts) — the key terms you need to know
- [Quickstart](/specstar/quickstart/) — the fastest path to a working app
