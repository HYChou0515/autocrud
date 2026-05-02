---
name: specstar-spec
description: Spec-driven authoring for SpecStar projects. Use when the user wants to add, modify, or regenerate spec-driven resources — e.g. "add a User resource", "I edited spec.md, regenerate", "/specstar", "/specstar regen", "my spec.md and _generated.py drifted". Translates brief prose into a curated `spec.md`, then into declarative `_generated.py` + `spec.lock.json`. Use it whenever spec.md, _generated.py, or spec.lock.json appear in the task. Do not use for runtime debugging of generated routes — that is the resource-manager / route-templates skill territory.
---

# SpecStar Spec-Driven Authoring

Translate user intent into the three artifacts of a spec-driven SpecStar project:

```
brief prose (chat input)
   ↓ this skill: expand + diff + confirm
spec.md
   ↓ this skill: write declarative Python (AST-validated)
my_app/_generated.py
   ↓ deterministic (no LLM)
spec.lock.json
```

Authoritative design: [docs/design/spec-driven-architecture.md](../../../docs/design/spec-driven-architecture.md).

---

## When to activate

- User invokes `/specstar` or `/specstar regen`.
- User describes a change to a resource ("add User", "rename email to email_address", "drop the deleted_at field on Order").
- User says "I edited spec.md, regenerate Python" or similar.
- User asks about drift between spec.md, _generated.py, or spec.lock.json.

When activated, **always** read the three core files first (next section). Never propose changes without first knowing the current state.

---

## Inputs — read in this order, every run

1. **`spec.md`** at project root. Authoritative human intent.
2. **`<package>/_generated.py`** — current declarative Python. Find the package by reading the `[project.scripts]` or recent imports if not obvious. Conventional name: `my_app/_generated.py`.
3. **`spec.lock.json`** — manifest with hashes + descriptor.
4. Optional: run `specstar status` (or `Bash(uv run specstar status)`) for the case classification.

If any of these is missing, the project may not be initialized. Suggest `specstar init` and stop.

---

## Decision tree by hash state (case 1–4)

After reading the three files (and ideally `specstar status`), classify:

| Case | spec.md vs lock | _generated.py vs lock | Action |
|---|---|---|---|
| **1** | match | match | No drift. Ask user for new intent (brief prose). |
| **2** | changed | match | Translate spec.md → updated `_generated.py`. Update lock. |
| **3** | match | changed | **Drift warning**. Ask user: revert generated, or promote changes back to spec.md. Do **not** silently overwrite. |
| **4** | both changed | both changed | **Reconcile mode**. List both diffs side-by-side, ask user which side wins per item. |

You **must not** proceed past a case-3 or case-4 without explicit user confirmation on resolution.

---

## Plan synthesis protocol (case 2 — the common path)

Given a brief prose request and the existing state, produce a plan in this exact format and present it to the user before writing anything:

```
Proposed changes:

  Resource: User
    + field: phone (str, optional)            ← new
    ~ field: email → unique=true              ← modified

  Permissions on Order:
    + delete: role=admin                      ← inferred (no permission section in prose)

Inferred decisions (review carefully):
  - phone is optional because prose did not mark it required
  - delete=admin is the SpecStar default for sensitive resources

Files to write:
  - spec.md                  (add Resource: User > phone)
  - my_app/_generated.py     (regenerate)
  - spec.lock.json           (regenerate)

Reply with `ok`, `confirm`, `yes`, or describe a correction.
```

**Hard rules**:

- **Every inferred decision is listed explicitly**. Never silently fill in a default.
- Breaking changes (rename, drop, type change, add-required) are flagged and require choosing a migration mechanism (declarative or scaffolded β-ref).
- For non-trivial logic (workers, complex permissions with DB lookups, cross-resource migrations), propose a **β reference**: a string like `"my_app.logic.process_order"` that points to a hand-written module. Scaffold the module with a `TODO: implement` body if it doesn't exist.

---

## Confirmation protocol

After presenting the plan, **wait for the user**. Acceptable approvals: `ok`, `yes`, `confirm`, `proceed`.

Anything else — `wait`, `but`, `no`, a question, a counter-proposal — sends you back to the plan stage. **Do not write files** until the user explicitly approves.

If the user says "use defaults" or "you decide", that is **not** approval to invent — it is a request to default the inferred decisions. List them explicitly anyway (so they're visible in the chat / commit) and await final `ok`.

---

## Write protocol

Once approved, in this order:

1. **Edit `spec.md`** to its new content. Preserve user prose; modify only the section being changed.
2. **Edit `<package>/_generated.py`** with declarative Python only. The body must be:
   - `spec.add_model(...)` calls
   - `Schema(...).step(...)` chains for migrations
   - `msgspec.Struct` class definitions
   - Pure-function migration bodies (input dict → output dict) when needed
   - References to user logic via **string identifiers** only (`"my_app.logic.fn"`), not `import`s of user modules
3. Run `Bash(uv run specstar verify)` to confirm AST + hashes.
4. If verify reports issues, **stop and report** — do not iterate without showing the user what failed.
5. If verify is green, the lock is in sync.

Note: `specstar verify` re-checks hashes against lock — but the lock won't be regenerated by this skill in v0.11; for that, after a successful Edit, regenerate via:

```bash
uv run python -c "
from <package> import _generated  # noqa
from specstar import spec
from specstar.lockfile import build_manifest, write_manifest, now_iso
from specstar.descriptor import ValidationStatus

manifest = build_manifest(
    spec.dump_descriptor(),
    sources={'spec.md': 'spec.md', '<package>/_generated.py': '<package>/_generated.py'},
    validation=ValidationStatus(ast_check='passed'),
    regenerated_at=now_iso(),
)
write_manifest(manifest, 'spec.lock.json')
"
```

(A dedicated `specstar gen` command will replace this stanza in a follow-up release.)

---

## Constraints — declarative Python only in `_generated.py`

The AST validator (`specstar.validator.DeclarativeASTValidator`) **will reject**:

- `import os` / `subprocess` / `socket` / `requests` / `urllib*` / `pathlib` / `shutil` / `threading` / `asyncio` / `ctypes` etc.
- `Try` / `With` / `Raise` / `While` / `Async*` / `Yield` / `Global` / `Nonlocal` statements
- Direct calls to `exec` / `eval` / `compile` / `open` / `__import__` / `input` / `breakpoint`

The validator **allows**: any non-blocked import, `If` / `For`, `Lambda`, comprehensions, attribute access, operator overloading, function and class definitions, basic builtins (`len`, `min`, `max`, `sorted`, `tuple`, `list`, `dict`, `set`, `range`, `enumerate`, `zip`, `bool`, `int`, `float`, `str`).

For a user-supplied behaviour that needs anything blocked (I/O, retry, orchestration), **do not write inline code** — emit a string `ref:` to a user module and scaffold the file separately.

If a generated function legitimately needs an exception you cannot avoid, append `# specstar: allow <reason>` on the same line. Use sparingly; every bypass is recorded in `spec.lock.json` for review.

---

## Failure recovery — never improvise

| Failure | Action |
|---|---|
| `specstar verify` reports AST errors | Show errors verbatim. Ask user how to proceed. Do **not** retry blind. |
| User says "no" / "wait" / corrects you | Discard plan; re-read state; propose new plan. |
| Drift detected (case 3 or 4) | List both sides; require explicit choice. |
| Lock seems corrupted / unparseable | Stop. Tell user. Suggest `specstar init --force` only if they confirm starting over. |
| Brief prose is ambiguous (e.g. field type unclear) | **Ask**. Never guess silently — guesses defeat the entire reliability story. |

---

## Worked example 1 — adding a resource

**User**: `add a User resource with name and email`

**Skill**:

```
Reading spec.md, my_app/_generated.py, spec.lock.json (case 1, clean).

Proposed changes:

  Resource: User                              ← new
    fields:
      - name: str (required)
      - email: str (required)

  Permissions:
    - read: any authenticated                 ← inferred (default)
    - delete: admin                           ← inferred (default for sensitive)
    - update: self or admin                   ← inferred
    - create: any authenticated               ← inferred

  Storage: project default                    ← inferred

Inferred (4 items): read/delete/update/create permissions.
No breaking changes.

Files to write: spec.md, my_app/_generated.py, spec.lock.json.

ok? (yes / no / refine)
```

User replies `yes`. Skill edits the three files, runs verify. If green, reports `done`.

---

## Worked example 2 — breaking change (rename)

**User**: `rename email to email_address on User`

**Skill**:

```
Reading inputs (case 2: spec.md unchanged, you'd like to edit it).

Proposed changes:

  Resource: User
    ~ rename field: email → email_address     ← BREAKING

This is a breaking change; existing data needs migration.

Migration options:
  [A] declarative rename (Schema(...).step(version, rename={"email": "email_address"}))
      ↑ recommended for pure renames
  [B] custom row-transform Python (I scaffold my_app/migrations/user_v1_to_v2.py
      with a TODO body; you implement it)
  [C] no versioning (existing data with field "email" will fail after this lands)

Choose [A]: ...
```

Wait for choice. After `[A]`, generate the Schema chain step in `_generated.py` and update spec.md `### Schema versions` section.

---

## Worked example 3 — drift reconcile (case 3)

**User**: (no message, but the user invoked `/specstar` and you find `_generated.py` modified without spec.md changes)

**Skill**:

```
Drift detected (case 3): you edited my_app/_generated.py without changing spec.md.

Differences in _generated.py vs lock:
  + new field: User.phone: str

This change is not reflected in spec.md. Two options:

  [A] revert _generated.py to match spec.md (I overwrite your edit)
  [B] promote your edit into spec.md (I edit spec.md to add User.phone)

Choose [A] or [B]:
```

Wait for choice. Never silently pick.

---

## Reference

- [docs/design/spec-driven-architecture.md](../../../docs/design/spec-driven-architecture.md) — strategic design (β heading protocol, descriptor schema, AST trust model, hash detection table)
- [docs/design/spec-driven-v0.11-plan.md](../../../docs/design/spec-driven-v0.11-plan.md) — implementation phases and acceptance criteria
- `specstar.validator.ast` — AST allow / block list
- `specstar.descriptor.types` — node / edge / manifest schemas
- `specstar.lockfile` — hash + manifest I/O
- CLI: `specstar init`, `specstar verify`, `specstar status`
