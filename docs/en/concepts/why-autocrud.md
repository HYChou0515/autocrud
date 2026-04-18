# Why AutoCRUD exists

AutoCRUD exists because many FastAPI backends spend too much effort rebuilding the same infrastructure around data.

That repeated work is often necessary, but it is rarely the part that makes a product unique.

---

## The recurring problem

A typical backend ends up maintaining the same layers over and over:

- CRUD routes
- validation and input shaping
- pagination and filtering
- search and indexing
- permissions
- audit history
- background jobs
- admin-facing operational tools

None of these are unimportant. The issue is that teams keep rewriting them from scratch even when the patterns are mostly the same.

---

## The shift in approach

AutoCRUD changes the development flow from:

$$
\text{build infrastructure first} \rightarrow \text{write domain logic later}
$$

to:

$$
\text{define the domain model} \rightarrow \text{let the framework generate the infrastructure}
$$

That makes the framework especially useful when you want consistent APIs without spending most of your time on repetitive plumbing.

---

## What problems it is trying to solve

AutoCRUD is a good fit when your project needs:

- repeatable CRUD APIs
- version-aware data handling
- consistent search behavior
- extension points for permissions and events
- optional job processing and admin workflows

It is particularly useful for:

- internal tools
- administrative systems
- content and configuration management
- operational dashboards
- job-oriented backend services

---

## What it is not trying to be

AutoCRUD is not intended to replace every backend style.

It is not primarily:

- a full event-sourcing platform
- a general workflow engine
- a distributed data mesh

Its value comes from making a common category of backend work simpler and more consistent.

---

## Where to go next

If you want the underlying model, continue with:

- [Overview](/autocrud/concepts/overview)
- [Core concepts](/autocrud/concepts/core-concepts)

If you want to start building right away, move to the quickstart and how-to guides.
