# Ubiquitous Language

## Resource lifecycle

| Term         | Definition                                                                       | Aliases to avoid              |
| ------------ | -------------------------------------------------------------------------------- | ----------------------------- |
| **Resource** | A model-driven domain entity managed by AutoCRUD.                                | Record, entity, row           |
| **Revision** | An immutable, versioned snapshot of a **Resource** at a point in time.           | Version, snapshot, history    |
| **Action**   | A named category of operation performed on a **Resource** (create, get, update). | Operation, verb               |
| **Phase**    | A point in the **Action** lifecycle: before, after, on_success, on_failure.      | Stage, step, hook point       |

## Events and handlers

| Term                  | Definition                                                                                       | Aliases to avoid                |
| --------------------- | ------------------------------------------------------------------------------------------------ | ------------------------------- |
| **Event**             | A specific (**Action**, **Phase**) point during a **Resource** operation.                        | Hook, signal, callback site     |
| **Event Context**     | The payload passed into an **Event Handler** describing the **Event** and its inputs/outputs.    | Payload, message, event data    |
| **Event Handler**     | A callable invoked by AutoCRUD when an **Event** fires.                                          | Listener, observer, callback   |
| **Builder Helper**    | The `do(...)` chain API that constructs **Event Handlers** from plain functions.                 | Factory, decorator, registrar  |
| **Permission Context**| A use-site alias for **Event Context** when the consumer is a permission check.                  | Auth context, request context  |

## Public API surface

| Term                  | Definition                                                                                                    | Aliases to avoid                       |
| --------------------- | ------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| **Public Namespace**  | A curated import path AutoCRUD users are expected to import from (e.g. `autocrud.events`, `autocrud.errors`). | Public API, top-level import           |
| **Canonical Owner**   | The single module where a symbol is *defined*, as opposed to where it is re-exported.                         | Source module, true home               |
| **Re-export Facade**  | A module that exists primarily to re-export symbols defined in other modules.                                 | Compat layer, umbrella module          |
| **Backward-Compat Shim** | A piece of code (e.g. PEP-562 `__getattr__`) that keeps a deprecated import path working.                  | Legacy alias, fallback                 |
| **Private Symbol**    | A name prefixed with `_` indicating it is not part of the public surface.                                     | Internal symbol, helper                |
| **Curated Namespace** | A **Public Namespace** whose contents are deliberately chosen via `__all__`, not the union of all imports.    | Vetted namespace, official API         |

## Refactor moves

| Term                  | Definition                                                                                                       | Aliases to avoid              |
| --------------------- | ---------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| **Cycle Break**       | A change that removes mutual imports between two modules so neither needs the other to finish initialising.     | Decoupling, untangle          |
| **Move**              | Relocating a **Canonical Owner** from one module to another. Implies updating callers; not just re-exporting.   | Migrate, transplant           |
| **Inline Import**     | A function-local `import` statement, often used to defer loading or hide circular dependencies.                  | Lazy import, deferred import  |

## Relationships

- An **Event** is uniquely identified by an (**Action**, **Phase**) pair.
- An **Event Context** carries the inputs of one **Action** at one **Phase**; the `EventContext` union covers every (Action, Phase) combination.
- An **Event Handler** is invoked by AutoCRUD whenever its supported **Event Context** is emitted.
- A **Builder Helper** produces one or more **Event Handlers** bound to specific (**Action**, **Phase**) pairs.
- A **Permission Context** is an **Event Context** consumed by a permission checker rather than by a logging/side-effect handler.
- A **Public Namespace** should re-export only symbols whose **Canonical Owner** is itself, except where it acts as an explicit, documented **Curated Namespace**.
- A **Re-export Facade** without a **Curated Namespace** contract is the seed of a **Backward-Compat Shim** and a likely **Cycle**.

## Example dialogue

> **Dev:** "If I `move` `IEventHandler` into `autocrud.events`, won't I lose the import path that uses `autocrud.types`?"

> **Maintainer:** "Yes, but that path was a **Re-export Facade** with no **Curated Namespace** behind it. The **Canonical Owner** for anything event-shaped should be `autocrud.events` — that's where the **Event Context** structs already live."

> **Dev:** "And the `__getattr__` at the bottom of `autocrud.events`?"

> **Maintainer:** "That's a **Backward-Compat Shim** that exists to dodge a **Cycle** with `autocrud.types`. Once we **Cycle Break** by moving `IEventHandler`, we delete it. No **Inline Import** needed."

> **Dev:** "What about callers that import `ResourceMetaSearchQuery` from `autocrud.types`?"

> **Maintainer:** "Same idea — `autocrud.query_types` is the **Canonical Owner**. `autocrud.types` should only re-export it if we explicitly mark it as a **Curated Namespace** with `__all__`. Otherwise update the callers."

## Flagged ambiguities

- **"events"** has been used to mean three different things in this conversation: (1) the lifecycle **Event** concept, (2) the `autocrud.events` **Public Namespace**, and (3) the `autocrud.resource_manager.events` private implementation module. Use **Event** for the concept, and prefix with the dotted path when referring to a module.
- **"do"** as a **Builder Helper** is too generic to discuss verbally; refer to it as the **Builder Helper** or `do(...) chain`, not "the do function".
- **"context"** has been used for both **Event Context** and **Permission Context**. They are the same underlying type but different consumer expectations — name the role explicitly when the distinction matters.
- **"move"** vs **"re-export"** — these are different operations. A **Move** changes the **Canonical Owner**; a re-export only adds an alias path. Cleaning up imports requires distinguishing them.
- **"public API"** — used loosely to mean both the package's `__init__.py` exports and any `Public Namespace`. Prefer **Public Namespace** when discussing per-module surfaces, and "package root" or "top-level public API" when referring to `autocrud/__init__.py`.
