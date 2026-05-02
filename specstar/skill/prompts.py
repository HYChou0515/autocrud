"""Prompt builders for the spec-driven authoring LLM call.

Both the Claude Code skill (`.claude/skills/specstar-spec/SKILL.md`) and the
``specstar gen`` CLI delegate the actual rules to this module. Keeping the
wording in one place prevents the two surfaces from drifting apart over
release cycles.

Design notes:

- The system prompt is a condensed restatement of the SKILL.md protocol —
  hard rules (declarative-only Python, AST allow/block list, every
  inferred decision listed explicitly, never improvise on failure) plus
  the case 1-4 decision tree.
- The user prompt embeds the current state (spec.md, _generated.py, lock
  metadata) verbatim — within reason. For projects that grow large, a
  later phase will add summarization; for v0.11 we expect spec.md to stay
  under a few thousand tokens.
- The output of :func:`build_messages` is a list of
  ``{"role": ..., "content": ...}`` dicts compatible with the Anthropic
  Python SDK ``messages.create`` API.
"""

from __future__ import annotations

from msgspec import Struct

from specstar.descriptor import Manifest


class AuthoringState(Struct, frozen=True):
    """Snapshot of the project state passed to the LLM.

    All three sources are passed verbatim so the LLM can compute its own
    diffs. ``manifest`` is supplied as a serialized JSON string for the
    same reason — the LLM does not need msgspec types in scope.
    """

    spec_md: str
    """Current contents of ``spec.md``."""

    generated_py: str
    """Current contents of ``<package>/_generated.py``."""

    manifest_json: str
    """Current ``spec.lock.json`` serialized as a JSON string."""

    package_name: str
    """The user's Python package (e.g. ``"my_app"``) — used to format
    file paths in instructions."""


SYSTEM_PROMPT = """\
You are the SpecStar spec-driven authoring engine. Your job is to translate \
brief user prose into a curated edit of `spec.md` and the corresponding \
declarative `_generated.py`. You do not write business logic.

## Hard rules (never violate)

1. `_generated.py` must contain **declarative Python only**:
   - `spec.add_model(...)` calls
   - `Schema(...).step(...)` chains
   - `msgspec.Struct` class definitions
   - Pure-function migration bodies (input dict → output dict)
   - String references for I/O / orchestration: `"my_app.logic.fn"`

2. **Forbidden in `_generated.py`** — the AST validator will reject:
   - imports of `os`, `subprocess`, `socket`, `requests`, `urllib*`, \
`pathlib`, `shutil`, `tempfile`, `threading`, `multiprocessing`, \
`asyncio`, `ctypes`, `httpx`, `aiohttp`, `http`
   - statements: `Try`, `With`, `Raise`, `While`, `AsyncFunctionDef`, \
`Await`, `Yield`, `Global`, `Nonlocal`
   - calls to `exec`, `eval`, `compile`, `open`, `__import__`, \
`input`, `breakpoint`, `getattr`, `setattr`, `delattr`
   - dunder attribute reads (`__class__`, `__bases__`, `__globals__`, \
`__builtins__`, ...) except `__name__` / `__doc__`
   - `import` of any user module — use string references instead

3. **Every inferred decision must be listed explicitly** in the plan you \
present to the user. Never silently fill in a default.

4. **Breaking changes** (rename, drop, type change, add-required) trigger \
a migration prompt. Choose declarative migration via `Schema(...).step(...)`\
 when possible; scaffold a `(β) ref` to a user module otherwise.

5. **Never improvise on failure.** If you don't understand the user's \
prose, ask. If the AST validator would reject your output, explain what \
failed and ask the user how to proceed. Do not retry blindly.

## spec.md format (β heading protocol)

```
# <Project>

## Resource: <Name>
<prose description>

### Fields
- `name`: <type>, <constraints>

### Permissions
- `<action>`: <rule>

### Storage
<optional>

### Workflows
- `<event>`: <description> → `my_app.logic.fn_name`

### Schema versions
<optional, only when versioned migrations exist>
```

## Decision tree by hash state

| Case | spec.md | _generated.py | Action |
|------|---------|---------------|--------|
| 1 | match | match | Ask user for new intent |
| 2 | changed | match | Translate spec.md → updated _generated.py |
| 3 | match | changed | Drift warning. Ask user: revert generated, or promote to spec.md |
| 4 | both changed | both changed | Reconcile mode — list both diffs, ask which side wins |

## Output format

Respond with two clearly labelled sections:

1. **Plan** — what you propose to do, with every inferred decision \
listed explicitly under a `Inferred decisions:` sub-heading.
2. **Confirmation request** — the literal text \
`Reply with 'ok' to apply, or describe a correction.`

Do **not** write the file edits in your response — that happens after \
the user confirms.
"""


def build_system_prompt() -> str:
    """Return the system prompt verbatim. Pure function; cheap to call."""
    return SYSTEM_PROMPT


def build_user_prompt(brief: str, state: AuthoringState) -> str:
    """Construct the user message embedding the brief plus current state.

    Format:

    ```
    BRIEF:
    <brief>

    PACKAGE: <package_name>

    spec.md:
    ```
    <contents>
    ```

    <package>/_generated.py:
    ```
    <contents>
    ```

    spec.lock.json (manifest):
    ```
    <contents>
    ```

    Produce a plan per the system prompt. Do not write files yet.
    ```
    """
    parts = [
        f"BRIEF:\n{brief.strip()}",
        f"PACKAGE: {state.package_name}",
        "spec.md:",
        f"```markdown\n{state.spec_md}\n```",
        f"{state.package_name}/_generated.py:",
        f"```python\n{state.generated_py}\n```",
        "spec.lock.json (manifest):",
        f"```json\n{state.manifest_json}\n```",
        "Produce a plan per the system prompt. Do not write files yet.",
    ]
    return "\n\n".join(parts)


def build_messages(
    brief: str,
    state: AuthoringState,
) -> list[dict[str, str]]:
    """Return Anthropic-API-compatible messages for the planning call.

    The system prompt is **not** included here — pass it via the SDK's
    ``system=`` parameter alongside this messages list. Splitting them
    matches Anthropic's prompt-caching boundaries (the system prompt is
    long-lived; user messages are per-turn).
    """
    return [
        {
            "role": "user",
            "content": build_user_prompt(brief, state),
        }
    ]


def state_from_paths(
    *,
    spec_md_path,
    generated_py_path,
    manifest: Manifest | None,
    package_name: str,
) -> AuthoringState:
    """Convenience constructor that reads the three sources from disk.

    Pass ``manifest=None`` when no lock file exists yet (e.g. a freshly
    initialised project where the user invokes ``specstar gen`` before
    the first lock has been built). The manifest section will be replaced
    with an explanatory placeholder.
    """
    from pathlib import Path

    import msgspec.json

    spec_md = Path(spec_md_path).read_text(encoding="utf-8")
    generated_py = Path(generated_py_path).read_text(encoding="utf-8")
    if manifest is not None:
        manifest_blob = msgspec.json.format(
            msgspec.json.encode(manifest), indent=2
        ).decode("utf-8")
    else:
        manifest_blob = '{"note": "no spec.lock.json exists yet"}'

    return AuthoringState(
        spec_md=spec_md,
        generated_py=generated_py,
        manifest_json=manifest_blob,
        package_name=package_name,
    )
