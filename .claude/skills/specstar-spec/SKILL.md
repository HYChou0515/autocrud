---
name: specstar-spec
description: Spec-driven authoring for SpecStar projects. Two-step pipeline — intent.md (user prose) → spec.md (structured β protocol) → _generated.py (declarative Python, runtime SSOT). Use when the user wants to add, modify, or regenerate spec-driven resources — e.g. "add a User resource", "I edited intent.md, regenerate", "/specstar", "/specstar regen", "spec.md and _generated.py drifted". Use whenever intent.md, spec.md, _generated.py, or spec.lock.json appear in the task. Do not use for runtime debugging of generated routes — that is the resource-manager / route-templates skill territory.
---

# SpecStar Spec-Driven Authoring

Two-step LLM pipeline:

```
intent.md (user free prose)
   │
   │ STEP 1 — translate prose to structured spec
   ▼
spec.md (β heading protocol — LLM-generated, human-reviewable)
   │
   │ STEP 2 — translate spec to declarative Python
   ▼
<package>/_generated.py (runtime SSOT)
```

The user can edit **any** layer — SpecStar's edit-respect logic detects manual edits at each layer and skips the LLM step that would overwrite them.

`_generated.py` is the **runtime source of truth**: the engine runs whatever this file declares. `intent.md` and `spec.md` are documentation/intent layers — they may lag in informal sessions, but `specstar verify` enforces alignment in CI.

Authoritative design: [docs/design/spec-driven-architecture.md](../../../docs/design/spec-driven-architecture.md).

---

## When to activate

- User invokes `/specstar` or `/specstar regen`.
- User edits `intent.md` and wants the downstream files updated.
- User edits `spec.md` directly and wants `_generated.py` updated.
- User edits `_generated.py` directly and wants the lock refreshed.
- User describes a change in chat ("add a User resource", "rename email to email_address").
- User asks about drift between any of the four files.

When activated, **always read** the four files (next section) before proposing anything.

---

## Inputs — read in this order, every run

1. **`intent.md`** at project root. The user's free prose.
2. **`spec.md`** at project root. Structured β-protocol spec (current state).
3. **`<package>/_generated.py`** — declarative Python. Find package via `[project.scripts]` or recent imports. Conventional name: `my_app/_generated.py`.
4. **`spec.lock.json`** — manifest with per-source SHA-256 hashes plus the descriptor.

If any of these is missing, the project may not be initialised. Suggest `specstar init` and stop.

---

## Hash decision tree (which step to run)

Compare each file's current hash to its entry in `spec.lock.json.sources[*].sha256`:

| `intent.md` | `spec.md` | `_generated.py` | STEP 1 (intent→spec) | STEP 2 (spec→py) | Action |
|---|---|---|---|---|---|
| match | match | match | skip | skip | clean — ask user for new intent |
| **changed** | match | match | run | run | both regenerate |
| match | **changed** | match | skip | run | user took over spec — only regen py |
| match | match | **changed** | skip | skip | user took over py (SSOT) — only refresh lock |
| **changed** | **changed** | match | **skip** | run | user took over spec; respect it; regen py |
| match | **changed** | **changed** | skip | **skip** | user took over both downstream — only refresh lock |
| **changed** | match | **changed** | run | **prompt user** | spec changed via STEP 1 but py was hand-edited; conflict |
| **changed** | **changed** | **changed** | skip | skip | full reconcile mode — list diffs and ask |

**Hard invariant**: an LLM step never overwrites a downstream file the user has manually edited. Conflict cases require explicit user choice; never silently pick.

`--force` flag (passed by the user) bypasses cache and edit-respect; STEP 1 + STEP 2 both run unconditionally.

---

## STEP 1 plan synthesis

Inputs to the LLM call:
- `intent.md` content (the user's goal)
- previous `spec.md` content (for breaking-change detection)
- package name

Output schema: `SpecPlan` (Pydantic).

Required fields in the plan you present to the user:

```
Proposed STEP 1 changes:

  Resources:
    + Resource: User                 ← new
      + field: name (str, required)
      + field: email (str, required)

  Inferred decisions:
    - User.permissions.delete = role(admin)   (default for sensitive resources)
    - User.permissions.read = any authenticated   (CRUD default)

  Breaking changes:
    (none)

  Files to write: spec.md
```

Wait for `ok` / `confirm`. Then write `spec.md`.

If breaking changes are detected, your plan must include a `### Schema versions` entry in the proposed `spec.md` describing the migration in prose.

---

## STEP 2 plan synthesis

Inputs to the LLM call:
- current `spec.md` content (the structured spec to translate)
- previous `_generated.py` content (for stability — preserve helper names, import order)
- package name

Output schema: `PythonPlan` (Pydantic). Note: `PythonPlan` has no `spec_md_after` field — STEP 2 cannot modify spec.md by construction.

Required fields in the plan:

```
Proposed STEP 2 changes:

  my_app/_generated.py
    + class User(msgspec.Struct)
    + spec.add_model(User, name="user")
    + permission setup ...

  Inferred decisions (during Python translation):
    (none — direct mapping from spec.md)

  Files to write: my_app/_generated.py
```

Wait for `ok`. Then write `_generated.py`.

---

## Confirmation protocol

After presenting either step's plan, **wait for the user**. Acceptable approvals: `ok`, `yes`, `confirm`, `proceed`.

Anything else (`wait`, `but`, `no`, a question, a counter-proposal) sends you back to the plan stage. **Do not write files** until the user explicitly approves.

If the user says "use defaults" or "you decide", that is **not** approval to invent — it is a request to default the inferred decisions. List them explicitly anyway and await final `ok`.

---

## Write protocol

After approval:

1. **STEP 1 only**: write the new `spec.md`. (Don't yet touch `_generated.py`.)
2. **STEP 2 only**: write the new `_generated.py`. (Don't yet touch `spec.md`.)
3. After all writes for the run are done, run `Bash(uv run specstar lock)` to refresh `spec.lock.json` (re-hash every source, re-snapshot descriptor, re-run AST validator).
4. Run `Bash(uv run specstar verify)` to confirm green.

If `lock` reports `ast_check=failed`, surface the validator errors verbatim and ask the user how to proceed (typically: move offending code into a hand-written module and reference it by string from spec.md).

---

## Constraints — declarative Python only in `_generated.py`

The AST validator (`specstar.validator.DeclarativeASTValidator`) **will reject**:

- Imports of `os`, `subprocess`, `socket`, `requests`, `urllib*`, `pathlib`, `shutil`, `tempfile`, `threading`, `multiprocessing`, `asyncio`, `ctypes`, `httpx`, `aiohttp`, `http`. Also: any user package — use string references instead.
- Statements: `Try`, `With`, `Raise`, `While`, `AsyncFunctionDef`, `Await`, `Yield`, `Global`, `Nonlocal`.
- Direct calls to: `exec`, `eval`, `compile`, `open`, `__import__`, `input`, `breakpoint`, `getattr`, `setattr`, `delattr`.
- Dunder attribute reads except `__name__` and `__doc__`.

For I/O / orchestration / external calls, emit a string reference like `"my_app.logic.process_order"` — do NOT `import` user modules.

If a generated function legitimately needs an exception you cannot avoid, append `# specstar: allow <reason>` on the same line. Use sparingly; every bypass is recorded in `spec.lock.json` for review.

---

## Failure recovery — never improvise

| Failure | Action |
|---|---|
| `specstar lock` reports AST errors | Show errors verbatim. Ask user how to proceed. Do **not** retry blind. |
| User says "no" / "wait" / corrects you | Discard plan; re-read state; propose new plan. |
| Drift conflict (case 6/7/8) | List the two sides; require explicit choice. Default in non-interactive mode: respect downstream (SSOT). |
| Lock seems corrupted / unparseable | Stop. Tell user. Suggest `specstar init --force` only if they confirm starting over. |
| User prose ambiguous | **Ask**. Never guess silently — guesses defeat the entire reliability story. |

---

## Worked example 1 — fresh project, user describes intent

**User**: edits `intent.md` to add: "We have orders that belong to users."

**Skill** (after `/specstar regen`):

```
Reading inputs...
  intent.md hash CHANGED (vs lock)
  spec.md hash matches lock
  my_app/_generated.py hash matches lock
→ STEP 1 + STEP 2 will run.

Proposed STEP 1 changes:

  Resources:
    + Resource: Order              ← new
      + field: user_id (str, ref to user, required)
      + field: amount (int, required)

  Inferred decisions:
    - Order.permissions.delete = role(admin)         (default)
    - Order.permissions.create = any authenticated    (CRUD default)
    - user_id field type is str (consistent with User's id)

  Breaking changes: (none)

  Files to write: spec.md

ok? (yes / no / refine)
```

User: `yes`. Skill writes spec.md.

```
Proposed STEP 2 changes:

  my_app/_generated.py:
    + class Order(msgspec.Struct):
    +     user_id: Annotated[str, Ref("user")]
    +     amount: int
    + spec.add_model(Order, name="order")

  Files to write: my_app/_generated.py

ok?
```

User: `yes`. Skill writes _generated.py, then runs `specstar lock` + `specstar verify`. Both green → reports `done`.

---

## Worked example 2 — user edited spec.md directly

**State**: user added a section to spec.md by hand. `intent.md` unchanged.

**Skill** (on `/specstar regen`):

```
Reading inputs...
  intent.md hash matches lock
  spec.md hash CHANGED (vs lock)
  my_app/_generated.py hash matches lock
→ STEP 1 SKIPPED (you took control of spec.md).
→ STEP 2 will run.

Proposed STEP 2 changes:
  ...

ok?
```

STEP 1 is skipped by design — intent.md unchanged, but more importantly **the user's manual spec.md edit is preserved**.

---

## Worked example 3 — drift conflict (case 7)

**State**: user edited intent.md AND _generated.py. spec.md unchanged.

**Skill**:

```
Reading inputs...
  intent.md hash CHANGED
  spec.md hash matches lock
  my_app/_generated.py hash CHANGED
→ STEP 1 will run (intent changed, spec unchanged → safe to regen spec).
   But STEP 2 conflicts: spec will change, but _generated.py was
   hand-edited.

Conflict: STEP 1 will produce a new spec.md, but you've also edited
_generated.py. Two options:

  [A] Run STEP 1 + STEP 2; STEP 2 will overwrite your _generated.py
      changes with translation from the new spec.md.
  [B] Skip STEP 2; keep your _generated.py edits. spec.md regenerates
      but _generated.py stays as you wrote it. (You'll need to manually
      reconcile drift later.)

Choose [A] or [B]:
```

Wait for choice. Never silently pick.

---

## Reference

- [docs/design/spec-driven-architecture.md](../../../docs/design/spec-driven-architecture.md) — strategic design (β heading protocol, descriptor schema, AST trust model, two-step pipeline rationale)
- `specstar.skill.prompts` — STEP1_SYSTEM_PROMPT and STEP2_SYSTEM_PROMPT verbatim (also used by `specstar gen` CLI)
- `specstar.skill.schemas` — SpecPlan and PythonPlan Pydantic models
- `specstar.validator.ast` — AST allow / block list
- `specstar.descriptor.types` — node / edge / manifest schemas
- `specstar.lockfile` — hash + manifest I/O
- CLI: `specstar init`, `specstar gen`, `specstar lock`, `specstar verify`, `specstar status`
