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
    """Construct the STEP 2 user message embedding spec + previous python."""
    return _join(
        f"PACKAGE: {state.package_name}",
        "spec.md (the structured spec to translate):",
        f"```markdown\n{state.spec_md}\n```",
        "Previous _generated.py (for stability — preserve idioms unless they need to change):",
        f"```python\n{state.previous_generated_py}\n```",
        f"Produce PythonPlan with the new {state.package_name}/_generated.py content.",
    )


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
