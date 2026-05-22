# Spec-Driven Authoring

> **Status**: introduced in v0.11. Additive — your existing `spec.add_model(User, ...)` Python keeps working unchanged.

SpecStar v0.11 introduces a spec-driven authoring layer on top of the existing engine. You describe resources in **prose** (`intent.md`), a two-step LLM pipeline writes a structured spec (`spec.md`), then declarative Python (`_generated.py`) that the engine consumes.

```text
intent.md                       ← your free prose, never overwritten
   ↓ STEP 1: skill / specstar gen --call
spec.md                         ← structured β heading protocol
   ↓ STEP 2: same pipeline, AST-validated
<package>/_generated.py         ← declarative Python, runtime SSOT
   ↓ deterministic (spec.dump_descriptor)
spec.lock.json                  ← hashes + descriptor + validation status
```

The engine is unchanged: `spec.add_model(...)`, `Schema(...).step(...)`, route templates, storage, permissions all behave exactly as before. Spec-driven is an authoring layer on top.

---

## TL;DR

```bash
# 1. Bootstrap a starter project
uv run specstar init my_app

# 2. Edit intent.md to describe what you want, then either:
#    a. In Claude Code: invoke /specstar
#    b. From any provider: specstar gen --call --provider openai --model gpt-4o
uv run specstar gen --call --provider openai --model gpt-4o --yes

# 3. CI-friendly drift check (no LLM)
uv run specstar verify
```

---

## The four artifacts

| File | Authoritative? | Edited by | Tracked in git? |
|---|---|---|---|
| `intent.md` | yes — your prose | you | yes |
| `spec.md` | derived | LLM (STEP 1) | yes |
| `<package>/_generated.py` | runtime SSOT | LLM (STEP 2) | yes |
| `spec.lock.json` | derived | `specstar lock` | yes |
| `pyproject.toml` `[tool.specstar]` | yes | you | yes |
| `.env` / `.env.example` | secrets / template | you | only `.env.example` |

`_generated.py` is committed so PR review can see exactly what the model registration looks like. `spec.lock.json` is committed so `specstar verify` (CI) detects drift.

---

## `spec.md` — the β heading protocol

Three heading levels matter; everything else is prose.

```markdown
# My App                     ← project title (one per spec.md)

## Project                   ← optional, project-wide scalars
- model_naming: snake
- admin: root@example.com

## Resource: User            ← per-resource section
A registered user.

### Fields                   ← required
- `name`: required string
- `email`: required, unique, format=email

### Permissions              ← optional — uses 6 controlled tokens
- read: authenticated
- update: owner
- delete: admin

### Workflows                ← optional — phase + action + dotted ref
- after create: my_app.logic.send_welcome_email

### Indexes                  ← optional
- email
- name

### Defaults                 ← optional
- default_status: draft
- default_user: anonymous
- default_now: utc
- id_generator: uuid4
- encoding: json

### Storage                  ← optional — omit to use project default
backend: postgres
dsn: env DATABASE_URL

### Schema versions          ← only when you have versioned migrations
#### v1 → v2: rename email to email_address
Migration: rename only.

### Validation               ← optional — string ref to user code
- my_app.logic.validate_user

### Constraints              ← optional — list of string refs
- my_app.logic.no_duplicate_email
```

Full vocabulary lookup: see [spec.md syntax reference](../reference/spec-md-syntax.md).

---

## Feature toggles

Each spec.md section maps to a **feature flag** in `pyproject.toml`. When a flag is off, STEP 2 leaves that section's content as a comment in `_generated.py` instead of writing real code.

```toml
[tool.specstar]
features = ["permissions", "workflows", "schema"]
```

Default: `["permissions", "workflows", "schema"]` (the three pure-declarative essentials).

Widen as you adopt more surface:

```toml
features = [
    "permissions", "workflows", "schema",
    "indexes", "defaults", "encoding", "id_generator",
    "storage", "mq", "blob",
    "validators", "constraints",
]
```

Per-run override: `--feature storage` (add) / `--no-feature workflows` (remove). See [How-to: feature toggles](../howto/spec-driven-features.md).

---

## Secrets and `.env`

Spec-driven `_generated.py` cannot `import os` — the AST validator blocks it. To reference deployment env vars (DB URLs, S3 buckets, JWT keys), use `specstar.env(...)`:

```python
from specstar import BackendBinding, BackendConfig, spec
import specstar

spec.configure(
    backend=BackendConfig(
        connections={
            "main": ConnectionProfile(
                type="postgres",
                options={"dsn": specstar.env("DATABASE_URL")},
            ),
        },
        meta=BackendBinding(use="main"),
        resource=BackendBinding(use="main"),
    ),
)
```

`specstar init` scaffolds `.env.example` (committed) and `.gitignore` (lists `.env`). Copy `.env.example` to `.env`, fill in real values, never commit `.env`. Production environments inject env vars directly — `.env` is dev-only.

Full walkthrough: [How-to: env vars in spec-driven projects](../howto/spec-driven-features.md#env-vars).

---

## Daily workflow

```bash
# Make a change
$EDITOR intent.md

# Regenerate
specstar gen --call --provider openai --model gpt-4o --yes

# Inspect the diff
git diff spec.md my_app/_generated.py spec.lock.json

# Run / test
uvicorn my_app:app
```

In Claude Code, replace step 2 with `/specstar` — same pipeline, no API key needed.

Both paths share:

- the same prompts (`specstar.skill.prompts`)
- the same feature toggles
- the same AST validator
- the same lock file

---

## Recovery and self-healing

The `gen --call` pipeline ships three safety layers:

| Trigger | Behavior |
|---|---|
| LLM produces invalid Python | AST validator rejects pre-write — nothing lands on disk |
| LLM-generated code imports cleanly but errors at runtime (TypeError, missing kwarg) | **Feedback retry**: captured stderr is fed back to STEP 2 as additional prompt context, LLM self-corrects up to `--feedback-retries N` (default 2) times |
| Feedback retries exhausted | Rollback: working tree restored to pre-call state; user sees the error and the LLM output that triggered it |
| `rm spec.lock.json` | Treated as "rebuild from scratch" — `force=True` reruns STEP 1 + STEP 2 from `intent.md` |
| `rm spec.md` | Same as missing lock — STEP 1 recreates from intent.md |

---

## What the skill is allowed to write

The skill writes **declarative Python only** into `_generated.py`:

- `spec.configure(...)` once at file top (when storage / mq / blob / project scalars are used)
- `spec.add_model(...)` calls
- `msgspec.Struct` class definitions
- `Schema(...).step(...)` chains + pure-function migration bodies
- Imports of: `specstar`, `msgspec`, `typing`, `enum`, `datetime`, `decimal`
- Built-in helpers: `specstar.env(...)`, `specstar.string_ref(...)`, `specstar.defaults.utcnow`, `specstar.id_generators.uuid4`, the 5 permission `CheckFunc` builtins, `StringRefEventHandler`, `StringRefConstraintChecker`

The skill **never** writes:

- `import os` / `subprocess` / `socket` / `requests` / `urllib*` / `pathlib` / `httpx` etc.
- `Try` / `With` / `Raise` / `While` / `Async` statements
- `exec`, `eval`, `compile`, `open`, `__import__`, `getattr`, `setattr`, `delattr`
- Dunder reads other than `__name__` / `__doc__`
- Imports of any user package — use string references

Anything needing user logic (validators, event handler bodies, custom permission checks) lives in your own module under `<package>/logic/` and is referenced from spec.md by dotted path.

---

## Logic references (β pattern)

For business logic, write hand-coded Python in your own module and reference it from spec.md:

```markdown
### Workflows
- after create: my_app.logic.send_welcome_email
```

Your `my_app/logic.py`:

```python
def send_welcome_email(context) -> None:
    # idempotency, retry, side effects: your responsibility
    user = context.data
    smtp_send(user.email, subject="Welcome", body=f"Hi {user.name}")
```

The skill **does not** generate this body. STEP 2 emits a `StringRefEventHandler("my_app.logic.send_welcome_email", phase="after", action=ResourceAction.create)` in `_generated.py`. The dotted path is resolved lazily on first dispatch — your function doesn't need to exist when `specstar lock` runs.

This is the **β (beta) pattern**: clear separation between *what* (declared in spec.md) and *how* (your Python).

The string-ref wrapper class depends on the slot:

| add_model kwarg | Wrapper |
|---|---|
| `event_handlers` | `specstar.events.StringRefEventHandler` |
| `constraint_checkers` | `specstar.resource_manager.StringRefConstraintChecker` |
| `validator` | `specstar.string_ref("...")` (works directly) |
| `id_generator` | `specstar.string_ref("...")` |
| `default_user` (callable form) | `specstar.string_ref("...")` |

---

## CLI commands

| Command | Purpose | Uses LLM? | Modifies files? |
|---|---|---|---|
| `specstar init [PACKAGE]` | Bootstrap a starter project | no | yes (creates) |
| `specstar status` | Show current drift state | no | no |
| `specstar verify` | CI: pass/fail on drift + AST | no | no |
| `specstar lock` | Rebuild `spec.lock.json` from current files | no | yes (lock only) |
| `specstar gen --step {1,2}` | Print prompts for one step (dry-run) | no | no |
| `specstar gen --call` | Full pipeline — STEP 1 + STEP 2 + apply + lock + verify | yes | yes |

Use `verify` in CI; `status` interactively while editing; `gen --call` to actually regenerate.

---

## Drift detection (the 8-case table)

`specstar status` classifies the three tracked files against the lock:

| Case | intent | spec | gen | What `gen --call` does |
|---|---|---|---|---|
| 1 | clean | clean | clean | Nothing — refresh lock |
| 2 | changed | clean | clean | Run STEP 1 + STEP 2 |
| 3 | clean | changed | clean | Run STEP 2 only (respect user spec edits) |
| 4 | clean | clean | changed | Refresh lock only (`_generated.py` is SSOT — user wins) |
| 5 | changed | changed | clean | STEP 2 only — user's spec edits win over intent.md |
| 6 | clean | changed | changed | Refresh lock only — spec/gen both diverged, neither overrides the other |
| 7 | changed | clean | changed | STEP 1 only — leave user's `_generated.py` alone, regenerate spec.md |
| 8 | changed | changed | changed | Refresh lock only — full divergence, reconcile manually or `--force` |

`--force` re-runs STEP 1 + STEP 2 unconditionally. `--from-spec` skips STEP 1 (use when spec.md is hand-written).

---

## LLM providers

`specstar gen --call` uses [litellm](https://github.com/BerriAI/litellm) under the hood, so any provider it supports works:

```bash
# Anthropic (default)
specstar gen --call --provider anthropic --model claude-sonnet-4-6

# OpenAI
specstar gen --call --provider openai --model gpt-4o

# OpenAI-compatible self-host (Ollama, vLLM, LM Studio, ...)
specstar gen --call --provider openai-compatible \
    --base-url http://localhost:11434/v1 \
    --model llama3.1
```

API keys read from env (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`) or `--api-key` flag.

---

## Reliability — what "spec-driven" promises

1. **The skill writes declarative Python only.** It never generates business logic — that's always your hand-written module.
2. **An AST validator** (`specstar.validator.DeclarativeASTValidator`) rejects any non-declarative pattern in `_generated.py` **before** anything lands on disk. See [AST validator reference](../reference/ast-rules.md).
3. **Pre-write rollback** restores the working tree if `lock` or `verify` rejects the LLM output post-write — your `_generated.py` and `spec.md` revert to their pre-call content.
4. **Feedback retry** turns runtime errors (TypeError, missing kwarg, hallucinated symbol) into self-correction rounds before falling back to rollback.
5. **A property-graph descriptor** (`spec.lock.json`) makes every change auditable in PR review — reviewers see structured node/edge changes, not a wall of generated Python.
6. **CI runs `specstar verify`** which is fully deterministic (no LLM). It re-hashes sources, re-checks AST, and fails the build if any artifact has drifted.

Every LLM call is human-in-the-loop. Every artifact is reviewable. Every drift is detectable in CI.

---

## Migration story for existing v0.10 users

Three paths — pick whichever matches your appetite:

- **A. Don't migrate.** Your `spec.add_model(User, ...)` Python keeps working. v0.11 is purely additive.
- **B. Mix.** Add new resources via `intent.md` / `spec.md`. Old resources stay where they are. Both kinds of `add_model` calls coexist on the same `spec` instance.
- **C. Full migration.** Wait for v1.x's `specstar init --from-existing` reverse-engineering tool. Not in v0.11.

There are **no breaking changes** in v0.11.

---

## See also

- [Spec.md syntax reference](../reference/spec-md-syntax.md) — full β protocol lookup
- [How-to: feature toggles](../howto/spec-driven-features.md) — pyproject.toml, CLI flags, env vars
- [AST validator reference](../reference/ast-rules.md) — what the skill is allowed to emit
- [`docs/design/spec-driven-architecture.md`](https://github.com/HYChou0515/specstar/blob/master/docs/design/spec-driven-architecture.md) — strategic design rationale
