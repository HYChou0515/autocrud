# Spec-Driven Authoring

> **Status**: introduced in v0.11. Additive — your existing `spec.add_model(User, ...)` Python keeps working unchanged.

SpecStar v0.11 introduces a spec-driven authoring layer on top of the existing engine. You describe resources in **prose** (`spec.md`), and a Claude Code skill — or the `specstar gen` CLI — translates your intent into the declarative Python that the engine consumes.

```text
brief prose (chat)
   ↓ skill: expand + diff + confirm
spec.md
   ↓ skill: write declarative Python (AST-validated)
my_app/_generated.py
   ↓ deterministic (spec.dump_descriptor)
spec.lock.json
```

The engine is unchanged: `spec.add_model(...)`, `Schema(...).step(...)`, route templates, storage backends, permissions all behave exactly as before. Spec-driven is an authoring layer on top.

---

## TL;DR

```bash
# 1. Bootstrap a starter project
uv run specstar init my_app

# 2. Edit spec.md to describe resources, then in Claude Code:
/specstar regen

# 3. CI-friendly drift check (no LLM)
uv run specstar verify
```

---

## The three artifacts

| File | Authoritative? | Edited by | Tracked in git? |
|---|---|---|---|
| `spec.md` | **yes** — single source of truth | skill (curated), occasional human | yes |
| `<package>/_generated.py` | derived | skill only — **don't hand-edit** | yes |
| `spec.lock.json` | derived | skill only | yes |

`_generated.py` is committed so PR review can see exactly what the model registration looks like. `spec.lock.json` is committed so `specstar verify` (CI) can detect drift.

---

## `spec.md` — the β heading protocol

Three heading levels matter; everything else is prose.

```markdown
# My App                     ← project title (one per spec.md)

## Resource: User            ← per-resource section
A registered user.

### Fields                   ← five fixed sub-sections; omit any not needed
- `name`: required string
- `email`: required, unique, format=email

### Permissions
- `read`: any authenticated
- `delete`: admin only

### Workflows
- `on_create`: send welcome email → `my_app.logic.send_welcome_email`

### Storage                  (omit to use project defaults)
postgres meta, s3 blob

### Schema versions          (only when you have versioned migrations)
#### v1 → v2: rename email to email_address
Migration: declarative — rename only.
```

Section content can be prose, bullets, tables — anything readable. The skill normalizes these into structured Python.

---

## Daily workflow with Claude Code

1. **Edit `spec.md`** in your editor (or just describe the change in chat).
2. **In Claude Code**: invoke `/specstar` (or describe the change directly — the skill triggers on phrases like "add User resource"). The skill:
   - reads `spec.md`, `_generated.py`, `spec.lock.json`
   - classifies the project state (clean / spec.md changed / generated changed / both changed)
   - presents a plan with **every inferred decision listed explicitly**
   - waits for your `ok` / `confirm`
   - writes `_generated.py` and updates `spec.lock.json`
3. **Inspect the diff** in your editor or PR — review the proposed `_generated.py` change like any other code.
4. **Commit all three files** (`spec.md`, `_generated.py`, `spec.lock.json`).

---

## What the skill is allowed to write

The skill writes **declarative Python only** into `_generated.py`:

- `spec.add_model(...)` calls
- `msgspec.Struct` class definitions
- `Schema(...).step(...)` chains
- Pure-function migration bodies (input dict → output dict)
- String references to user logic — `"my_app.logic.process_order"`

The skill **never** writes:

- I/O code (network, filesystem, subprocess)
- Workers / event handlers / orchestration
- Try / With / Raise statements
- Imports of operating-system or networking modules

If your business logic needs any of those, write it yourself in a separate Python module and reference it from `spec.md` by name. See [Logic references](#logic-references-β-pattern) below.

---

## Logic references (β pattern)

For anything beyond pure data shape, write hand-coded Python in your own module and reference it from `spec.md`:

```markdown
### Workflows
- `on_create`: send confirmation email → `my_app.logic.workers.process_order`
```

Your `my_app/logic/workers.py`:

```python
from specstar.types import WorkerContext

def process_order(order, ctx: WorkerContext) -> None:
    # idempotency, retry, side effects: your responsibility
    send_confirmation_email(order.user_email)
    charge_card(order.user_id, order.total)
    mark_order_paid(order.id)
```

The skill **does not** generate this body. It only:

- emits the string reference into `_generated.py`
- verifies the symbol exists at codegen time
- scaffolds a `TODO: implement` body if the file doesn't yet exist

This is the `β` (beta) pattern in the design doc: clear separation between *what* (declared in `spec.md`) and *how* (your Python).

---

## CLI commands

| Command | Purpose | Uses LLM? | Modifies files? |
|---|---|---|---|
| `specstar init [PACKAGE]` | Bootstrap a starter project | no | yes (creates) |
| `specstar status` | Show drift case 1/2/3/4 | no | no |
| `specstar verify` | CI: pass/fail on drift + AST | no | no |
| `specstar gen` *(coming)* | Skill-equivalent for non-Claude-Code users | yes | yes |

Use `verify` in CI; `status` interactively while editing.

---

## Drift detection (case 1 / 2 / 3 / 4)

`specstar status` classifies your project against the lock file:

| Case | spec.md | `_generated.py` | What to do |
|---|---|---|---|
| 1 | match | match | Nothing — clean state |
| 2 | changed | match | Run the skill to regenerate Python |
| 3 | match | changed | You hand-edited `_generated.py`. Either revert, or promote your edit into spec.md |
| 4 | both | both | Reconcile with the skill — it lists differences side-by-side |

The skill never silently picks a side in case 3 or 4. It always asks.

---

## Migration story for existing v0.10 users

Three paths — pick whichever matches your appetite:

- **A. Don't migrate.** Your `spec.add_model(User, ...)` Python keeps working. v0.11 is purely additive.
- **B. Mix.** Add new resources via `spec.md` + skill. Old resources stay where they are. Both kinds of `add_model` calls coexist on the same `spec` instance.
- **C. Full migration.** Wait for v1.x's `specstar init --from-existing` reverse-engineering tool. Not in v0.11.

There are **no breaking changes** in v0.11. If you upgrade and don't change anything, your tests still pass.

---

## Reliability — what "spec-driven" promises

The trust story behind the skill rests on four layers:

1. **The skill writes declarative Python only.** It never generates business logic — that's always your hand-written module.
2. **An AST validator** (`specstar.validator.DeclarativeASTValidator`) rejects any non-declarative pattern in `_generated.py`. See [AST validator reference](../reference/ast-rules.md) for the allow / block list.
3. **A property-graph descriptor** (`spec.lock.json`) makes every change auditable in PR review — reviewers see structured node/edge changes, not a wall of generated Python.
4. **CI runs `specstar verify`** which is fully deterministic (no LLM). It re-hashes sources, re-checks AST, and fails the build if any artifact has drifted.

Every LLM call is human-in-the-loop. Every artifact is reviewable. Every drift is detectable in CI.

---

## See also

- [AST validator reference](../reference/ast-rules.md) — what the skill is allowed to emit
- [`docs/design/spec-driven-architecture.md`](https://github.com/HYChou0515/specstar/blob/master/docs/design/spec-driven-architecture.md) — strategic design rationale
- [`docs/design/spec-driven-v0.11-plan.md`](https://github.com/HYChou0515/specstar/blob/master/docs/design/spec-driven-v0.11-plan.md) — implementation plan
