# Spec-Driven Feature Toggles

In a spec-driven project you decide which SpecStar surface the LLM is allowed to generate code for. Toggles live in `pyproject.toml`. CLI flags override per run.

When a feature is **on**, STEP 2 translates the matching spec.md section into real `add_model` / `spec.configure` code.

When a feature is **off**, the same section's content is preserved as a comment block in `_generated.py`. You can adopt features incrementally without losing intent.

---

## Where toggles live

```toml
# pyproject.toml
[tool.specstar]
features = ["permissions", "workflows", "schema"]
```

`specstar init` scaffolds this file. The default list is conservative — three pure-declarative features that need no env vars or external deps.

---

## Full feature catalogue

| Feature flag | spec.md section | What it generates |
|---|---|---|
| `permissions` | `### Permissions` | `permission_checker=ActionBasedPermissionChecker.from_dict({...})` |
| `workflows` | `### Workflows` | `event_handlers=[StringRefEventHandler(...)]` |
| `schema` | `### Schema versions` | `Schema(Cls, "vN").step(...)` chain |
| `indexes` | `### Indexes` | `indexed_fields=[...]` |
| `defaults` | `### Defaults` (most bullets) | `default_status=`, `default_user=` |
| `encoding` | `### Defaults > encoding` | `encoding=Encoding.json\|msgpack` |
| `id_generator` | `### Defaults > id_generator` | `id_generator=specstar.id_generators.uuid4` or `specstar.string_ref(...)` |
| `storage` | `### Storage` + `## Project` | `spec.configure(backend=BackendConfig(...))` |
| `mq` | `### Message queue` | adds `mq=BackendBinding(...)` to the same spec.configure |
| `blob` | `### Blob` | adds `blob=BackendBinding(...)` |
| `validators` | `### Validation` | `validator=specstar.string_ref(...)` |
| `constraints` | `### Constraints` | `constraint_checkers=[StringRefConstraintChecker(...)]` |

---

## Enable / disable per project

Edit `pyproject.toml`:

```toml
[tool.specstar]
features = [
    "permissions", "workflows", "schema",
    "indexes", "defaults",
    "storage", "mq",   # newly adopted
]
```

Then run `specstar gen --call` — the LLM will start emitting code for the newly-enabled features. Existing code for already-enabled features is preserved.

---

## Per-run override

`--feature NAME` adds for this run only (on top of pyproject):

```bash
specstar gen --call --feature storage --feature mq
```

`--no-feature NAME` removes:

```bash
specstar gen --call --no-feature workflows
```

Both flags are repeatable. `--no-feature` wins when both reference the same name.

---

## Empty list = "no features"

`features = []` differs from omitting the key:

| `pyproject.toml [tool.specstar].features` | Resolved features |
|---|---|
| omitted | the framework default (`permissions`, `workflows`, `schema`) |
| `[]` | empty — every section preserved as comment, nothing generated |
| `["permissions"]` | only permissions |

---

## Confirm what the LLM will see

Dry-run shows the exact STEP 2 prompt that `--call` would send, including the "Enabled features" preamble:

```bash
specstar gen --step 2 | head -30
```

Look for:

```
## Enabled features

Generate `add_model` kwargs only for these features: permissions, workflows, schema.
For spec.md sections describing features NOT in this list, leave the content as
a Python comment in `_generated.py` (do not invent kwargs).
```

The list reflects the resolved value (pyproject + CLI overrides). Dry-run is free — no LLM call, no API key needed.

---

## env vars

Several features (`storage`, `mq`, `blob`) need credentials. The pipeline supplies them via `specstar.env(...)`, which reads `os.environ` and lazy-loads `./.env` on first call.

### dev: `.env`

```bash
# .env (gitignored — `specstar init` adds this to .gitignore)
DATABASE_URL=postgresql://user:pass@localhost:5432/my_app_dev
S3_BUCKET=my-app-dev
AMQP_URL=amqp://guest:guest@localhost:5672/
```

`specstar gen --call` and the runtime both pick these up automatically.

### production: container env

In production (k8s, docker, heroku), no `.env` file exists. Inject env vars at the container layer; `specstar.env()` reads them directly via `os.environ`. Container env always wins over `.env` content — 12-factor convention.

### Required vs optional

```python
# Required — raises KeyError at runtime if unset
specstar.env("DATABASE_URL")

# Optional — falls back to default
specstar.env("PORT", default="8000")
```

`specstar init` scaffolds `.env.example` showing which keys your project uses. Commit `.env.example`; never commit `.env`.

---

## Why disable a feature?

Common cases:

- **Adopting incrementally.** Start with the default three; widen as the team gets comfortable with each generated pattern.
- **Debugging.** `--no-feature workflows` for one run to verify a permission issue isn't masked by event handler noise.
- **Pinning style.** A team that hand-writes its own permission checkers can set `features = ["workflows", "schema"]` to keep STEP 2 from regenerating their permission code.

---

## See also

- [Spec-Driven Authoring guide](../guides/spec-driven.md) — the broader workflow
- [Spec.md syntax reference](../reference/spec-md-syntax.md) — every section + its tokens
- [AST validator reference](../reference/ast-rules.md) — what `_generated.py` may import / call
