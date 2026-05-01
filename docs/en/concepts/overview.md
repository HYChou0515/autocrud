# Overview

This page is the **system map** for SpecStar.

Its purpose is to show how the major pieces fit together before you dive into the details.

If you are new to the project, a good reading order is: **Overview → Core Concepts → Architecture → Resource Lifecycle**.

---

## The shortest mental model

At a high level, the workflow looks like this:

1. define a Python model
2. register it with SpecStar
3. let SpecStar create the operational layer around it
4. expose the result through FastAPI routes and OpenAPI

That operational layer includes revision tracking, metadata handling, validation flow, and optional search or UI generation.

---

## The main building blocks

### Resource

A resource is the logical entity your application manages, such as a user, document, job, or configuration object.

### Revision

A revision is one version of that resource over time.

### ResourceManager

The ResourceManager is the component that applies lifecycle rules such as validation, revision creation, permissions, and storage access.

### Route templates

Route templates generate the API surface for each resource, so common CRUD behavior does not need to be wired manually.

### Storage layers

SpecStar separates metadata, revision data, and blobs so storage strategies can stay flexible.

---

## What this means in practice

A minimal app often looks like this:

```python
from fastapi import FastAPI
from msgspec import Struct

from specstar import crud


class User(Struct):
    name: str
    email: str


app = FastAPI()
crud.add_model(User)
crud.apply(app)
```

From that small definition, SpecStar can generate the repetitive infrastructure needed for a usable API.

---

## Read next

- [Why SpecStar exists](/specstar/concepts/why-specstar) — the motivation and problem statement
- [Core concepts](/specstar/concepts/core-concepts) — the key terminology
- [Architecture](/specstar/concepts/architecture) — the component-level view
- [Resource lifecycle](/specstar/concepts/resource-lifecycle) — how resources evolve over time
