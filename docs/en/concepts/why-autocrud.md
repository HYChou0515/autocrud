# Why AutoCRUD exists

This page explains the **motivation** behind AutoCRUD.

If you want the system map, read [Overview](/autocrud/concepts/overview). If you want precise terminology, read [Core concepts](/autocrud/concepts/core-concepts).

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

## The model-driven shift

AutoCRUD changes the development flow from:

$$
\text{build infrastructure first} \rightarrow \text{write domain logic later}
$$

to:

$$
\text{define the domain model} \rightarrow \text{generate the infrastructure around it}
$$

That shift is most useful when you want predictable APIs and operational behavior without spending most of the project on plumbing.

---

## Problems AutoCRUD is trying to reduce

AutoCRUD is a good fit when your project needs:

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

AutoCRUD is not trying to replace every backend style.

It is not primarily:

- a full event-sourcing platform
- a general workflow engine
- a distributed data mesh
- a traditional server-rendered full-stack framework

Its value comes from making a common class of API-centric backend work simpler and more consistent.

---

## Read next

- [Overview](/autocrud/concepts/overview) — the high-level system map
- [Core concepts](/autocrud/concepts/core-concepts) — the key terms you need to know
- [Quickstart](/autocrud/quickstart/) — the fastest path to a working app
