# `spec.md` Syntax Reference

The β heading protocol used by `specstar gen --call` and the Claude Code `/specstar` skill. This page is the canonical lookup table.

If you want a walkthrough, read [Spec-Driven Authoring](../guides/spec-driven.md) first.

---

## Heading levels

| Level | Meaning | Required? | Cardinality |
|---|---|---|---|
| `# <Project Title>` | Project name | yes | one per file |
| `## Project` | Project-wide scalars | no | zero or one |
| `## Resource: <Name>` | One resource | yes (at least one) | one per resource |
| `### <Section>` | Sub-section of a resource | varies | see table below |

---

## `## Project` block (project-wide scalars)

Optional. Lifts into the `spec.configure(...)` call at the top of `_generated.py`.

| Bullet | Translates to | Notes |
|---|---|---|
| `- model_naming: snake` | `model_naming="snake"` | One of: `same` / `pascal` / `camel` / `snake` / `kebab` |
| `- admin: root@example.com` | `admin="root@example.com"` | Used by RBAC + the `admin_only` built-in CheckFunc |
| `- strict_operation_context: true` | `strict_operation_context=True` | When on, writes raise if user/now aren't resolved |
| `- graphql: on` | (comment only — wire in `__init__.py`) | Needs `pip install specstar[graphql]` |
| `- cors: allow_origins=["..."]` | (comment only — wire in `__init__.py`) | Middleware order matters |

---

## `### Fields` — required

Each resource must have at least one field. One bullet per field.

```markdown
### Fields
- `title`: required string
- `isbn`: optional string
- `price`: required number
- `stock`: required integer, default 0
- `user_id`: required string, ref to `user` on_delete cascade
```

Translates to a `msgspec.Struct` class definition. Refs become `Annotated[str, Ref("user", on_delete=OnDelete.cascade)]`.

---

## `### Permissions` — 6-token controlled vocabulary

Feature flag: `permissions` (in default `DEFAULT_FEATURES`).

```markdown
### Permissions
- read: authenticated
- update: owner
- delete: admin
- permanently_delete: denied
- export: custom: my_app.permission.export_check
```

| Token | Maps to | Behavior |
|---|---|---|
| `public` | `specstar.permission.any_user` | Anyone, including anonymous |
| `authenticated` | `specstar.permission.any_authenticated` | Any non-anonymous user |
| `admin` | `specstar.permission.admin_only` | Matches `DEFAULT_ROOT_USER` (overrideable via `## Project: admin`) |
| `owner` | `specstar.permission.owner_self` | `context.user == meta.created_by` |
| `denied` | `specstar.permission.deny_all` | Always deny |
| `custom: <dotted>` | `specstar.string_ref("<dotted>")` | Escape hatch — your CheckFunc |

Translates to:

```python
permission_checker=ActionBasedPermissionChecker.from_dict({
    ResourceAction.read: any_authenticated,
    ResourceAction.update: owner_self,
    ResourceAction.delete: admin_only,
    ResourceAction.permanently_delete: deny_all,
    ResourceAction.export: specstar.string_ref("my_app.permission.export_check"),
})
```

---

## `### Workflows` — event handlers

Feature flag: `workflows` (default).

Each bullet must declare **phase** + **action** + **dotted string ref**:

```markdown
### Workflows
- after create: my_app.logic.notify_customers_new_book
- before delete: my_app.logic.archive_book
- on_success update: my_app.logic.invalidate_cache
- on_failure create: my_app.logic.alert_oncall
```

| Phase | Fires |
|---|---|
| `before` | Before the operation; can raise to abort |
| `after` | After the operation (always, even on failure) |
| `on_success` | Only on success |
| `on_failure` | Only on failure |

Translates each bullet into a `StringRefEventHandler(target, phase=..., action=ResourceAction.<X>)` entry in `event_handlers=[...]`. The dotted target is resolved lazily on first dispatch — your `my_app/logic.py` doesn't need to exist when `specstar lock` runs.

---

## `### Indexes` — searchable fields

Feature flag: `indexes` (opt-in; not in default).

```markdown
### Indexes
- email
- name
- created_at
```

Translates to `indexed_fields=["email", "name", "created_at"]`. The runtime uses this list for search query indexing.

---

## `### Defaults` — `default_*` kwargs

Feature flags: `defaults`, `encoding`, `id_generator` (each opt-in).

```markdown
### Defaults
- default_status: draft
- default_user: anonymous
- default_now: utc
- id_generator: uuid4
- encoding: json
```

| Bullet | Translates to |
|---|---|
| `default_status: draft\|stable` | `default_status=RevisionStatus.draft\|stable` |
| `default_user: <literal>` | `default_user="<literal>"` |
| `default_user: specstar.env("X")` | `default_user=specstar.env("X")` |
| `default_now: utc` | `default_now=specstar.defaults.utcnow` |
| `default_now: Asia/Taipei` | `default_now=specstar.defaults.now("Asia/Taipei")` |
| `default_now: <dotted>` | `default_now=specstar.string_ref("<dotted>")` |
| `id_generator: uuid4` | `id_generator=specstar.id_generators.uuid4` |
| `id_generator: <dotted>` | `id_generator=specstar.string_ref("<dotted>")` |
| `encoding: json\|msgpack` | `encoding=Encoding.json\|msgpack` |

---

## `### Storage` — `spec.configure(backend=...)`

Feature flag: `storage`.

```markdown
### Storage
- backend: postgres
- dsn: env DATABASE_URL
- table_prefix: app_
```

| Backend | Required options | Translates to |
|---|---|---|
| `memory` | none | `BackendBinding(type="memory")` |
| `disk` | `rootdir` | `options={"rootdir": ...}` |
| `postgres` | `dsn` | `options={"dsn": specstar.env("DATABASE_URL")}` |
| `s3` | `bucket`, `region` | `options={"bucket": specstar.env("S3_BUCKET"), ...}` |

When `### Storage` is set, STEP 2 emits a `spec.configure(backend=BackendConfig(...))` call at the **top** of `_generated.py` (before any `add_model` call). If both `### Storage` and `## Project` blocks are set, both lift into the same `spec.configure(...)` call as additional kwargs.

---

## `### Message queue` — `mq=BackendBinding(...)`

Feature flag: `mq`.

```markdown
### Message queue
- backend: rabbitmq
- amqp_url: env AMQP_URL
```

| Backend | Required options | Notes |
|---|---|---|
| `simple` | none | In-process, dev-only |
| `rabbitmq` | `amqp_url` | Production-ready |

Lifts into the same `spec.configure(backend=BackendConfig(..., mq=BackendBinding(...)))` call.

---

## `### Blob` — `blob=BackendBinding(...)`

Feature flag: `blob`.

```markdown
### Blob
- backend: s3
- bucket: env S3_BUCKET
```

| Backend | Required options |
|---|---|
| `memory` | none |
| `disk` | `rootdir` |
| `s3` | `bucket` |

Same lift pattern — joins the project-level `spec.configure(...)` call.

---

## `### Schema versions` — migrations

Feature flag: `schema` (default).

```markdown
### Schema versions
#### v1 → v2: rename `email` to `email_address`
The user's email column is renamed.
Migration: rename only — `email` → `email_address`.
```

Each `#### vX → vY` becomes a `Schema(...).step("vX", _migrate_vX_to_vY)` entry. Pure-function migrations are inlined in `_generated.py`; complex migrations route to `my_app.logic.<fn>` via string ref.

**Gotcha:** when `Schema` is the first positional to `add_model`, **don't** also pass `validator=`. Set the validator on `Schema(Cls, "v", validator=...)` instead.

---

## `### Validation` — single validator

Feature flag: `validators`.

```markdown
### Validation
- my_app.logic.validate_book
```

Translates to `validator=specstar.string_ref("my_app.logic.validate_book")`. Called at create/update time; safe to leave the user function unwritten until first dispatch.

---

## `### Constraints` — list of constraint checkers

Feature flag: `constraints`.

```markdown
### Constraints
- my_app.logic.no_duplicate_isbn
- my_app.logic.price_must_be_positive
```

Each bullet becomes a `StringRefConstraintChecker(target)` entry in `constraint_checkers=[...]`. Each user function must accept `(data, *, exclude_resource_id=None) -> None`.

---

## Cross-resource refs

Refs are declared **inline** in `### Fields`:

```markdown
### Fields
- `user_id`: required string, ref to `user` on_delete cascade
- `prev_order`: optional string, ref_revision to `order`
```

Translates to:

```python
class Order(msgspec.Struct):
    user_id: Annotated[str, Ref("user", on_delete=OnDelete.cascade)]
    prev_order: Annotated[str | None, RefRevision("order")] = None
```

`on_delete` options: `cascade` / `set_null` / `restrict`.

---

## Comments and prose

Anything outside the recognized headings is **prose** and is preserved verbatim in spec.md but ignored by STEP 2. Use it for design rationale, examples, or notes to future you.

```markdown
## Resource: Order

An order is a customer's purchase basket. We store one per checkout
event so analytics can reconstruct the history later.

### Fields
- ...
```

The paragraph between `## Resource: Order` and `### Fields` shows up in `spec.md` and stays as a top-of-resource docstring in `_generated.py` (when feasible) — review-friendly without affecting runtime behavior.

---

## See also

- [Spec-Driven Authoring guide](../guides/spec-driven.md) — full workflow walkthrough
- [How-to: feature toggles](../howto/spec-driven-features.md) — pyproject.toml + CLI control
- [AST validator reference](ast-rules.md) — what `_generated.py` may import / call
