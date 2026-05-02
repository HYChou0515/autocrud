# AST Validator Reference

The `specstar.validator.DeclarativeASTValidator` enforces that `_generated.py` (the skill-maintained file in spec-driven projects) contains **declarative Python only** — no I/O, no orchestration, no side effects.

`specstar verify` runs the validator on every `*_generated.py` it finds in `spec.lock.json`. CI fails on the first violation.

This page is the canonical reference for what the validator accepts and rejects.

---

## Mental model

Three layers cooperate to keep generated code safe:

1. **API design** — declarative slots (`spec.add_model`, permission expressions, query filters) accept proxy types whose operator overloading produces expression trees instead of computing values.
2. **AST validation** — the file as a whole passes through an allow / block list before any of it runs.
3. **String references** — anything that needs I/O lives in your own module and is referenced by name (`"my_app.logic.fn"`), not imported.

If the validator rejects something in `_generated.py`, the fix is almost always: move the offending logic into your own module, then reference it by string from `spec.md`.

---

## Block-list — rejected outright

### Imports

These top-level module names cause `import` and `from … import …` statements to fail:

| Module | Reason |
|---|---|
| `os` | filesystem, env, process |
| `subprocess` | shell |
| `socket` | network |
| `requests`, `urllib`, `urllib2`, `urllib3`, `httpx`, `aiohttp`, `http` | HTTP |
| `pathlib` | filesystem |
| `shutil`, `tempfile` | filesystem |
| `threading`, `multiprocessing`, `asyncio` | concurrency |
| `ctypes` | foreign function interface |

### Statements

| AST node | Why blocked |
|---|---|
| `Try` / `TryStar` | error handling implies failures, which implies I/O |
| `With` / `AsyncWith` | context managers usually wrap I/O |
| `Raise` | raising errors belongs in user logic, not declarative wiring |
| `While` | non-declarative control flow |
| `AsyncFunctionDef` / `Await` / `Yield` / `YieldFrom` | concurrency / generators |
| `Global` / `Nonlocal` | mutation patterns |

### Builtin calls

Direct calls to these names are blocked (they bypass the sandbox):

`exec`, `eval`, `compile`, `open`, `__import__`, `input`, `breakpoint`

---

## Allow-list — accepted

### Statements

- `Import` / `ImportFrom` — for any module **not** in the block-list (typically `specstar`, `msgspec`, `typing`, `enum`, `datetime`, `decimal`, your own user package as a *string ref*; never your user package as a Python `import`)
- `FunctionDef` — for declarative bodies (e.g. pure migration row-transforms)
- `ClassDef` — for `msgspec.Struct` definitions
- `Assign`, `AnnAssign`, `Return`
- `If`, `For`, `IfExp` — declarative wiring may legitimately loop or branch (e.g. registering a list of similar resources)
- `Pass`

### Expressions

`Lambda`, `Call`, `Attribute`, `BinOp`, `BoolOp`, `UnaryOp`, `Compare`, `IfExp`, list / dict / set / generator comprehensions, all literal types.

### Builtins (when called directly)

`len`, `min`, `max`, `sum`, `sorted`, `tuple`, `list`, `dict`, `set`, `frozenset`, `range`, `enumerate`, `zip`, `bool`, `int`, `float`, `str`.

(Other names, including any user-defined function in scope, are also allowed by the current skeleton — Phase 1.5 will tighten this with positive call-target tracking.)

---

## The escape hatch — `# specstar: allow`

Some violations are legitimate. Annotate the offending line with a comment to suppress the validator on that line:

```python
import os  # specstar: allow needs SPECSTAR_ENV at startup
```

The comment may include a free-text reason after `allow`. Pattern is case-insensitive and tolerates extra whitespace:

```python
try:  # SpecStar: Allow legacy retry block
    risky()
except Exception:
    fallback()
```

Bypassed lines are recorded in `spec.lock.json`'s `validation` block so reviewers can audit waivers.

**Use sparingly.** Each bypass is technical debt. If you find yourself reaching for it more than once or twice per file, move that code into a hand-written module and reference it from `spec.md` instead.

Same-line semantics only — above-line / block-scope exemption is intentionally not supported, to keep audit diffs unambiguous.

---

## When verify fails

`specstar verify` exits with code 1 and prints lines like:

```text
AST: my_app/_generated.py:3:0 [blocked_import] import of 'os' is not allowed in declarative Python
verify: 1 issue(s) detected
```

The fix:

1. Read the line cited in the error.
2. Decide whether the offending code is **declaration** (move it to spec.md) or **logic** (move it to your own Python module and reference it by string).
3. Re-run the skill to regenerate `_generated.py` with the corrected source-of-truth.

Do **not** silence violations with `# specstar: allow` to make CI green without thinking about why the validator flagged it.

---

## Reference

- Implementation: [`specstar.validator.ast`](https://github.com/HYChou0515/specstar/blob/master/specstar/validator/ast.py)
- Public API: `DeclarativeASTValidator`, `ValidationError`, `BLOCKED_IMPORTS`, `BLOCKED_STATEMENTS`, `BLOCKED_BUILTINS`
- Design rationale: [`docs/design/spec-driven-architecture.md`](https://github.com/HYChou0515/specstar/blob/master/docs/design/spec-driven-architecture.md) §3.2
