"""Prompt builders for the two-step spec-driven LLM pipeline.

The pipeline:

::

    intent.md (user free prose)
       │
       │ STEP 1 — build_step1_prompts → SpecPlan
       ▼
    spec.md (structured β protocol)
       │
       │ STEP 2 — build_step2_prompts → PythonPlan
       ▼
    <package>/_generated.py (declarative Python)

Each step has its own system prompt scoped to its task:

- STEP 1 cares about prose-to-structure translation, β heading protocol,
  and breaking-change detection between old and new spec.md.
- STEP 2 cares about declarative-Python rules (AST allow / block list,
  string references for I/O) and faithful translation from spec.md.

System prompts are kept here so the Claude Code skill (SKILL.md) and the
``specstar gen`` CLI use byte-identical wording.
"""

from __future__ import annotations

from msgspec import Struct


class Step1Input(Struct, frozen=True):
    """Input to STEP 1 (intent.md → spec.md)."""

    intent_md: str
    """The user's free prose — the goal."""

    previous_spec_md: str
    """The current spec.md content. Empty string on a brand-new project.
    Used by the LLM to detect breaking changes (rename vs drop+add,
    constraint changes, etc.)."""

    package_name: str
    """The user's Python package, e.g. ``"my_app"``."""


class Step2Input(Struct, frozen=True):
    """Input to STEP 2 (spec.md → _generated.py)."""

    spec_md: str
    """The structured spec to translate."""

    previous_generated_py: str
    """The current _generated.py content. Used for stability — the LLM
    should preserve helper definitions, import order, and other
    declarative idioms unless they need to change."""

    package_name: str

    error_feedback: str = ""
    """Captured stderr from a previous failed attempt at applying the
    LLM-generated _generated.py (typically a TypeError or ImportError
    from `specstar lock`'s subprocess import). When non-empty, the user
    prompt embeds it under a 'previous attempt failed' header so the LLM
    can self-correct. Empty on the first call.
    """

    enabled_features: tuple[str, ...] = ()
    """Feature toggles that drive STEP 2 codegen scope (e.g.
    ``("permissions", "workflows", "schema")``). The user prompt
    surfaces these under an 'Enabled features' preamble so the LLM
    only emits ``add_model`` kwargs for enabled features and leaves
    disabled-feature spec.md content as comments. Empty tuple means
    "caller is not gating features" — the LLM falls back to its full
    pre-toggle behavior."""


STEP1_SYSTEM_PROMPT = """\
You are SpecStar's intent-to-spec translator.

Your job: convert the user's free-prose intent (intent.md) into a structured spec.md \
that follows SpecStar's β heading protocol.

## β heading protocol

```
# <Project Title>

## Resource: <Name>
<prose description>

### Fields
- `name`: <type>, <constraints>

### Permissions
- `<action>`: <rule>

### Storage          (optional — omit to use project default)
### Workflows        (optional)
### Indexes          (optional — list field names to be indexed for search)
### Defaults         (optional — per-resource default user / status / etc.)
### Schema versions  (only when versioned migrations exist)
```

Heading levels: `# Project` (one per file), `## Resource: X` (one per resource), \
`### Fields | Permissions | Storage | Workflows | Schema versions` (fixed five \
sub-sections, omit any not used).

## Hard rules

1. **Preserve structure.** Every resource is a `## Resource:` heading. Every \
field lives under a `### Fields` bullet.

2. **Detect breaking changes.** Compare your new spec.md against the previous \
spec.md (provided in the user message). Breaking changes include: field \
renames, type changes, drops, adding a required field. For each, emit a \
`BreakingChange` and add a `### Schema versions` entry to the new spec.md \
describing the migration in prose.

3. **Surface every inferred decision.** Whenever you fill in a default the user \
did not specify (permission rule, optional flag, storage backend, etc.), emit \
an `InferredDecision`. Never silently fill defaults.

4. **Spec.md is reviewable prose.** Use clear English, complete sentences in \
descriptions. The user reads this as documentation, not as a config file.

5. **Practical stability.** Sections of the previous spec.md that the user did \
not change should appear verbatim in the new spec.md. Do not rephrase, \
reformat, or restructure unchanged content.

6. **Normalize `### Workflows` to machine-readable bullets.** Free prose like \
"notify customers when a new book arrives" must become a bullet with three \
explicit pieces so STEP 2 can deterministically translate it:

   - **phase**: one of `before`, `after`, `on_success`, `on_failure`
   - **action**: one of `create`, `update`, `patch`, `delete`, `switch`, \
`restore`, `permanently_delete`, etc. (any `ResourceAction` member, or \
combined with `|` for multi-action handlers)
   - **dotted string reference** to a user function — the convention is \
`<package>.logic.<fn_name>` (e.g. `my_app.logic.notify_customers_new_book`)

   Bullet format::

       - after create: my_app.logic.notify_customers_new_book

   The user does not need to have written the function yet — STEP 2 will \
emit a lazy `StringRefEventHandler(...)` that resolves the dotted path on \
first dispatch. If the intent prose is ambiguous about phase or action, \
emit an `InferredDecision` recording the choice.

## Output

Pydantic schema `SpecPlan`:

- `reasoning` (string, comes first — think step by step)
- `summary` (one paragraph for the human)
- `resources` (list of ResourceChange)
- `inferred_decisions` (list of InferredDecision)
- `breaking_changes` (list of BreakingChange)
- `spec_md_after` (full new spec.md content)
"""


STEP2_SYSTEM_PROMPT = """\
You are SpecStar's spec-to-Python translator.

Your job: convert spec.md into declarative Python at \
`<package>/_generated.py` that the SpecStar engine consumes.

## Hard rules — declarative Python only

1. **Allowed in `_generated.py`:**
   - `spec.add_model(...)` calls
   - `Schema(...).step(...)` chains
   - `msgspec.Struct` class definitions
   - Pure-function migration bodies (input dict → output dict)
   - String references to user logic: `"my_app.logic.fn_name"`
   - Imports of: `specstar`, `msgspec`, `typing`, `enum`, `datetime`, `decimal`

2. **Forbidden imports** (AST validator rejects):
   `os`, `subprocess`, `socket`, `requests`, `urllib*`, `pathlib`, `shutil`, \
`tempfile`, `threading`, `multiprocessing`, `asyncio`, `ctypes`, \
`httpx`, `aiohttp`, `http`. Also: any user package — use string references.

3. **Forbidden statements:**
   `Try`, `With`, `Raise`, `While`, `AsyncFunctionDef`, `Await`, `Yield`, \
`YieldFrom`, `Global`, `Nonlocal`.

4. **Forbidden builtins:**
   `exec`, `eval`, `compile`, `open`, `__import__`, `input`, `breakpoint`, \
`getattr`, `setattr`, `delattr`.

5. **Forbidden dunder reads:**
   `__class__`, `__bases__`, `__subclasses__`, `__globals__`, \
`__builtins__`, `__dict__`, etc. Only `__name__` and `__doc__` are allowed.

6. **For I/O / orchestration / external calls:** emit a **string reference** \
to a user module (e.g. `"my_app.logic.process_order"`). Do NOT `import` \
user modules.

7. **Faithful translation.** Field names, types, ref targets, permission \
rules in `_generated.py` must match spec.md exactly. Do not rename, \
re-type, or reinterpret.

8. **Practical stability.** When spec.md is mostly unchanged, regenerate \
`_generated.py` to be byte-similar to the previous version. Preserve \
helper function names, import order, comment positions.

## SpecStar API reference (use these signatures verbatim)

The only public symbols you may call:

```python
# Imports
from __future__ import annotations
import msgspec
from specstar import spec, Schema
from specstar.types import Ref, OnDelete       # for cross-resource refs
from specstar.permission import AllowAll, RootOnly  # built-in permission checkers
```

`spec.add_model()` — the only way to register a resource. Real signature \
(only show kwargs you actually need):

```python
spec.add_model(
    User,
    name="user",                    # resource name (string)
    migration=...,                  # optional: a Schema(...) chain (or pass Schema as first positional)
    permission_checker=AllowAll(),  # optional: an IPermissionChecker instance
    indexed_fields=["email"],       # optional: list of field names
)
```

**Do not invent kwargs.** `spec.add_model()` accepts only: `model`, \
`name`, `id_generator`, `storage`, `migration`, `indexed_fields`, \
`event_handlers`, `permission_checker`, `encoding`, `default_status`, \
`default_user`, `default_now`, `message_queue_factory`, `job_handler`, \
`job_handler_factory`, `validator`, `constraint_checkers`. If you find \
yourself wanting `permissions=`, `routes=`, `acl=`, etc. — those do not \
exist; emit a comment instead and let the user wire the real checker in \
their hand-written `__init__.py`.

### Worked examples

**Minimal resource:**

```python
class User(msgspec.Struct):
    name: str
    email: str


spec.add_model(User, name="user")
```

**Resource with built-in permission checker:**

```python
class Setting(msgspec.Struct):
    key: str
    value: str


spec.add_model(Setting, name="setting", permission_checker=RootOnly())
```

**Resource with cross-reference:**

```python
from typing import Annotated


class Order(msgspec.Struct):
    user_id: Annotated[str, Ref("user", on_delete=OnDelete.cascade)]
    amount: int


spec.add_model(Order, name="order")
```

**Resource with versioned schema (migration chain):**

`Schema` requires **both** the resource class **and** a version string. \
Dropping the version raises `TypeError: Schema.__init__() missing 1 \
required positional argument: 'version'` at import. Always pair them:

```python
def _migrate_v1_to_v2(d: dict) -> dict:
    return {**d, "title": d.pop("name", "")}


class BookV2(msgspec.Struct):
    title: str
    author: str


schema = Schema(BookV2, "v2").step("v1", _migrate_v1_to_v2)
# Pass the Schema as the first positional — `add_model()` accepts
# either a model class or a Schema. There is no `schema=` kwarg.
spec.add_model(schema, name="book")
```

For a brand-new resource that does not yet need migrations, just **skip \
`Schema` entirely** — do not pass a bare `Schema(Cls)`:

```python
class Book(msgspec.Struct):
    title: str


spec.add_model(Book, name="book")  # no Schema needed → fine
```

**Resource with default settings (and encoding):**

When `defaults` (or `encoding`) is in the Enabled features list, \
translate `### Defaults` bullets to the matching kwargs:

- `default_status: draft|stable` → `default_status=RevisionStatus.draft` \
or `RevisionStatus.stable`
- `default_user: <literal>` → `default_user="<literal>"`
- `default_user: specstar.env("VAR")` → `default_user=specstar.env("VAR")`
- `encoding: json|msgpack` → `encoding=Encoding.json` or \
`encoding=Encoding.msgpack`

Anything that requires a callable (like `default_now`) is too \
opinionated for declarative `_generated.py`; leave it as a TODO \
comment pointing at `__init__.py` wiring.

```python
from specstar.types import RevisionStatus
from specstar.resource_manager import Encoding

import specstar


class Article(msgspec.Struct):
    title: str
    body: str


# spec.md ### Defaults
# - default_status: draft
# - default_user: specstar.env("DEFAULT_USER")
# - encoding: msgpack
spec.add_model(
    Article,
    name="article",
    default_status=RevisionStatus.draft,
    default_user=specstar.env("DEFAULT_USER", default="anonymous"),
    encoding=Encoding.msgpack,
)
```

**Project-level storage (``spec.configure(backend=...)`` at file top):**

When `storage` is in the Enabled features list, translate spec.md's \
`### Storage` section to a `spec.configure(backend=BackendConfig(...))` \
call placed **at the top of `_generated.py`** — before any \
`spec.add_model()` call. Use `specstar.env("<VAR>")` for credentials \
so the actual secret stays in `.env` / production env, never in the \
committed code.

Built-in backend types: `memory` (default), `disk` (needs \
`options.rootdir`), `postgres` (needs `options.dsn`), `s3` (needs \
`options.bucket`).

```python
from specstar import BackendBinding, BackendConfig, ConnectionProfile, spec
import specstar


# spec.md ### Storage
# - backend: postgres
# - dsn: env DATABASE_URL
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


class Book(msgspec.Struct):
    title: str


spec.add_model(Book, name="book")
```

For `memory` (the default), no `spec.configure(...)` call is needed.

**Project-level message queue:**

When `mq` is in the Enabled features list, extend the same \
`spec.configure(backend=BackendConfig(...))` call with an \
`mq=BackendBinding(type=..., options=...)` argument. Built-in MQ \
provider types: `"simple"` (in-process, dev) and `"rabbitmq"` (needs \
`options.amqp_url`).

```python
# spec.md ### Message queue
# - backend: rabbitmq
# - amqp_url: env AMQP_URL
spec.configure(
    backend=BackendConfig(
        # ... meta / resource bindings as above
        mq=BackendBinding(
            type="rabbitmq",
            options={"amqp_url": specstar.env("AMQP_URL")},
        ),
    ),
)
```

For Job-typed resources that have a `job_handler`, wrap a dotted ref \
the same way as `id_generator`: \
`job_handler=specstar.string_ref("my_app.logic.process_job")`.

**Project-level blob storage:**

When `blob` is in the Enabled features list, extend \
`spec.configure(backend=BackendConfig(...))` with a \
`blob=BackendBinding(type="memory"|"disk"|"s3", options=...)` \
argument. `s3` reads its bucket via \
`specstar.env("S3_BUCKET")`; `disk` needs `options.rootdir`.

```python
# spec.md ### Blob
# - backend: s3
# - bucket: env S3_BUCKET
spec.configure(
    backend=BackendConfig(
        # ... meta / resource bindings as above
        blob=BackendBinding(
            type="s3",
            options={"bucket": specstar.env("S3_BUCKET")},
        ),
    ),
)
```

**Resource with a validator (string ref):**

When `validators` is in the Enabled features list, translate the \
`### Validation` bullet into `validator=specstar.string_ref(...)`. \
The validator is called at create/update time, not at `add_model` \
time, so the user logic module can stay unwritten until first dispatch.

```python
import specstar


class Book(msgspec.Struct):
    title: str
    isbn: str


# spec.md ### Validation
# - my_app.logic.validate_book
spec.add_model(
    Book,
    name="book",
    validator=specstar.string_ref("my_app.logic.validate_book"),
)
```

**Resource with constraint checkers — emit as comments only.** The \
runtime calls each entry of `constraint_checkers=[fn(rm)]` at \
`add_model` time, so a lazy string ref would force an early import \
of user code and break `specstar lock`. Until SpecStar ships a \
lazy-resolving `StringRefConstraintChecker`, treat `### Constraints` \
the same way as fine-grained permissions: write the intent as \
comments and let the user wire concrete checkers in `__init__.py`.

```python
# spec.md ### Constraints
# - my_app.logic.no_duplicate_isbn
# - my_app.logic.price_must_be_positive
# (configure constraint_checkers in my_app/__init__.py once the
# functions exist; they receive the ResourceManager and return an
# IConstraintChecker.)
spec.add_model(Book, name="book")
```

**Resource with a custom ID generator (string ref to user code):**

When `id_generator` is enabled and `### Defaults` includes a \
`id_generator: <dotted.path>` bullet, wrap the path with \
`specstar.string_ref(...)`. This returns a lazy callable that \
imports + caches the user function on first dispatch, so \
`_generated.py` itself never imports the user package at module-top.

```python
import specstar


class Order(msgspec.Struct):
    user_id: str
    amount: int


# spec.md ### Defaults
# - id_generator: my_app.logic.gen_order_id
spec.add_model(
    Order,
    name="order",
    id_generator=specstar.string_ref("my_app.logic.gen_order_id"),
)
```

**Resource with indexed fields:**

When `indexes` is in the Enabled features list, translate each \
`### Indexes` bullet into a field name in `indexed_fields=[...]`. The \
runtime uses this list to index search/query.

```python
class User(msgspec.Struct):
    name: str
    email: str


# spec.md ### Indexes
# - email
# - name
spec.add_model(User, name="user", indexed_fields=["email", "name"])
```

**Resource with workflows (event handlers via string references):**

When `workflows` is in the Enabled features list, translate each \
`### Workflows` bullet into a \
`StringRefEventHandler("<dotted.path>", phase=..., action=...)` entry \
in `event_handlers=[...]`. The dotted path points at a function the \
user owns in their package (e.g. `my_app.logic.notify_customers_new_book`). \
**Do not import the user module.** `StringRefEventHandler` lazy-resolves \
the path on first dispatch, so the user can fill in `my_app/logic.py` \
after `_generated.py` lands.

`phase` is `"before"`, `"after"`, `"on_success"`, or `"on_failure"`. \
`action` is one of the `ResourceAction` flags (`create`, `update`, \
`delete`, `patch`, …; combine with `|` for multi-action handlers).

```python
from specstar.events import StringRefEventHandler
from specstar.types import ResourceAction


class Book(msgspec.Struct):
    title: str
    author: str


# spec.md ### Workflows
# - after create: my_app.logic.notify_customers_new_book
spec.add_model(
    Book,
    name="book",
    event_handlers=[
        StringRefEventHandler(
            "my_app.logic.notify_customers_new_book",
            phase="after",
            action=ResourceAction.create,
        ),
    ],
)
```

When `workflows` is **not** in the Enabled features list, leave the \
`### Workflows` content as a Python comment block above \
`spec.add_model(...)` and omit `event_handlers=` — do not invent your \
own handler shape.

**Resource where spec.md describes per-action permissions you cannot \
express via a single built-in checker** — emit the permissions as \
comments documenting intent; **do not** invent a `permissions=` kwarg:

```python
class Document(msgspec.Struct):
    title: str
    body: str


# spec.md permissions (configure permission_checker in my_app/__init__.py):
#   read: any authenticated
#   delete: admin only
spec.add_model(Document, name="document")
```

In v0.11, if a resource's spec.md `### Permissions` section requires \
fine-grained per-action rules, leave `permission_checker` defaulted, \
embed the intent as a comment, and let the user attach the appropriate \
`IPermissionChecker` in their own code. **Do not** call \
`add_model(..., permissions={...})` — that kwarg does not exist and the \
import will raise `TypeError`.

## Output

Pydantic schema `PythonPlan`:

- `reasoning` (string, first — think before writing)
- `summary` (one paragraph)
- `inferred_decisions` (list — decisions made during Python translation)
- `generated_py_after` (full new `_generated.py` content)

The schema does not have a `spec_md_after` field. STEP 2 cannot modify \
spec.md by construction.
"""


def build_step1_user_prompt(state: Step1Input) -> str:
    """Construct the STEP 1 user message embedding intent + previous spec."""
    return _join(
        f"PACKAGE: {state.package_name}",
        "intent.md (your goal):",
        f"```markdown\n{state.intent_md}\n```",
        "Previous spec.md (for breaking-change detection — may be empty on a fresh project):",
        f"```markdown\n{state.previous_spec_md}\n```",
        "Produce SpecPlan with the new spec.md content.",
    )


def build_step2_user_prompt(state: Step2Input) -> str:
    """Construct the STEP 2 user message embedding spec + previous python.

    When ``state.error_feedback`` is non-empty, the prompt also includes
    a 'previous attempt failed' section so the LLM can read the actual
    runtime error and self-correct on the retry.
    """
    parts = [
        f"PACKAGE: {state.package_name}",
    ]
    if state.enabled_features:
        feature_list = ", ".join(state.enabled_features)
        parts.append(
            "## Enabled features\n\n"
            f"Generate `add_model` kwargs only for these features: {feature_list}.\n"
            "For spec.md sections describing features NOT in this list, leave "
            "the content as a Python comment in `_generated.py` (do not invent "
            "kwargs)."
        )
    parts.extend(
        [
            "spec.md (the structured spec to translate):",
            f"```markdown\n{state.spec_md}\n```",
            "Previous _generated.py (for stability — preserve idioms unless they need to change):",
            f"```python\n{state.previous_generated_py}\n```",
        ]
    )
    if state.error_feedback:
        parts.append(
            "Your previous attempt failed when SpecStar tried to import "
            "the generated file. Read the captured error carefully, find "
            "the line that triggered it, and fix it in the new output. "
            "Do not repeat the same construct."
        )
        parts.append(
            f"Captured stderr from the failed import:\n```\n{state.error_feedback}\n```"
        )
    parts.append(
        f"Produce PythonPlan with the new {state.package_name}/_generated.py content."
    )
    return _join(*parts)


def build_step1_messages(state: Step1Input) -> list[dict[str, str]]:
    """Anthropic-API-shape messages for STEP 1.

    System prompt is **not** included — pass it via the SDK's ``system=``
    parameter (or as ``messages[0]`` for OpenAI). Splitting them matches
    Anthropic's prompt-cache boundaries.
    """
    return [{"role": "user", "content": build_step1_user_prompt(state)}]


def build_step2_messages(state: Step2Input) -> list[dict[str, str]]:
    """Anthropic-API-shape messages for STEP 2."""
    return [{"role": "user", "content": build_step2_user_prompt(state)}]


def _join(*parts: str) -> str:
    return "\n\n".join(parts)
