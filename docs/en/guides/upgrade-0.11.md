# Upgrading to 0.11 (spec-driven authoring)

Version 0.11.0 introduces **spec-driven authoring** as an additive layer on top of the existing engine. There are **no breaking changes**: every existing v0.10 project continues to work unchanged.

If you don't want spec-driven authoring, ignore this page — `pip install -U specstar` and your code keeps running.

---

## What's new

### Engine API (unchanged)

| Surface | Status |
|---|---|
| `spec.add_model(...)` Python API | unchanged |
| `Schema(...).step(...)` migrations | unchanged |
| Route templates, storage, permissions, message queue | unchanged |

### New surface

| Surface | What it is |
|---|---|
| `spec.dump_descriptor()` | Emits a property-graph descriptor |
| `spec.lock.json` manifest | Hashes + descriptor + validation |
| `specstar` shell command | `init` / `verify` / `status` / `lock` / `gen` subcommands |
| `.claude/skills/specstar-spec/SKILL.md` | Claude Code authoring skill |
| AST validator | Protects spec-driven `_generated.py` files |

### New spec-driven helpers (importable from `specstar`)

| Symbol | Purpose |
|---|---|
| `specstar.env(name, *, default=None)` | Read env var; lazy-loads `./.env` |
| `specstar.string_ref(dotted)` | Lazy dotted-path callable wrapper |
| `specstar.defaults.utcnow` / `specstar.defaults.now(tz)` | Built-in `default_now=` values |
| `specstar.id_generators.uuid4` | Built-in `id_generator=` value |
| `specstar.events.StringRefEventHandler` | Lazy event handler from dotted ref |
| `specstar.resource_manager.StringRefConstraintChecker` | Lazy constraint checker |
| `specstar.permission.{any_user, any_authenticated, admin_only, owner_self, deny_all}` | 5 built-in `CheckFunc` for `ActionBasedPermissionChecker.from_dict` |

### `specstar gen --call` (LLM-driven authoring)

| Flag | Purpose |
|---|---|
| `--provider {anthropic,openai,openai-compatible}` | Pick the LLM transport |
| `--model NAME` | Model identifier for the provider |
| `--feature NAME` / `--no-feature NAME` | Per-run codegen scope override |
| `--feedback-retries N` | How many times to retry on LLM-output errors (default 2) |
| `--force` | Re-run STEP 1 + STEP 2 unconditionally |
| `--from-spec` | Skip STEP 1, run STEP 2 from current `spec.md` |

The complete workflow is documented in the [Spec-Driven Authoring guide](spec-driven.md).

---

## Three migration paths

Pick the one that matches your appetite.

### Path A — don't migrate

Do nothing. Your `spec.add_model(User, ...)` Python keeps working. v0.11 is purely additive.

The only thing you might notice is the `specstar` shell command being newly available. You don't have to use it.

### Path B — gradual mix

Run `specstar init` in a fresh directory to learn the workflow on a starter project, then incrementally:

1. Add **new** resources via `spec.md` + Claude Code skill `/specstar`.
2. Keep **existing** resources where they live (`my_app/models.py` or wherever).
3. Both kinds of `spec.add_model` calls coexist on the same global `spec` instance — there is no conflict.

Most existing users land here.

### Path C — full migration

Reverse-engineer your existing Python into `spec.md` form. **Not in v0.11.** A `specstar init --from-existing` tool is planned for v1.x. Stay on Path A or B until then.

---

## Quickstart on a new project

```bash
# Bootstrap
mkdir my_new_app && cd my_new_app
uv run specstar init my_app

# Files created:
#   intent.md                ← your free prose; edit this
#   spec.md                  ← LLM-generated structured spec
#   my_app/__init__.py       ← FastAPI app
#   my_app/_generated.py     ← LLM-maintained, runtime SSOT
#   spec.lock.json           ← deterministic, regenerated on lock
#   pyproject.toml           ← [tool.specstar] feature toggles
#   .env.example             ← committed; copy to .env
#   .gitignore               ← excludes .env

# Edit intent.md to describe your app, then either:
#   /specstar              (in Claude Code — no API key needed)
# or
#   specstar gen --call --provider openai --model gpt-4o --yes
#   specstar gen --call --provider anthropic --model claude-sonnet-4-6 --yes

# CI / drift check (no LLM)
uv run specstar verify

# Run the API
uvicorn my_app:app
```

---

## Behavioral changes to watch for

None. v0.11 ships zero breaking changes against the v0.10 public API.

That said, a few operational notes:

- The `specstar` shell command is **newly registered** in `pyproject.toml`. If you have shell aliases or scripts that defined a `specstar` of their own, they may now collide. Audit your `PATH`.
- The default starter (`specstar init`) creates `my_app/_generated.py` and `my_app/__init__.py`. If your existing project already has files at those paths, `specstar init` refuses to overwrite them — pass `--force` only when you mean it.
- `SpecStar.dump_descriptor()` is a **new** method. It does not collide with the existing `SpecStar.dump()` (which writes resource backups in msgpack format).

---

## Verifying the upgrade

```bash
uv run pytest                      # your existing test suite — should pass unchanged
uv run specstar --help             # shows the new init/verify/status subcommands
uv run python -c "from specstar import spec; print(spec.dump_descriptor())"
```

If any of these fail or surprise you, please open an issue.

---

## See also

- [Spec-Driven Authoring guide](spec-driven.md) — full workflow walkthrough
- [Spec.md syntax reference](../reference/spec-md-syntax.md) — every section + its tokens
- [How-to: feature toggles](../howto/spec-driven-features.md) — pyproject.toml + CLI control
- [AST validator reference](../reference/ast-rules.md) — what the skill is allowed to emit
- [`docs/design/spec-driven-architecture.md`](https://github.com/HYChou0515/specstar/blob/master/docs/design/spec-driven-architecture.md) — strategic design
