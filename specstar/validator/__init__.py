"""AST validator for skill-maintained ``_generated.py`` files.

The validator enforces that LLM-emitted code is **declarative-only** — pure
data construction calls into the SpecStar API, plus pure-function bodies for
constrained extension points (e.g. row-transform migrations). I/O,
orchestration, and side-effecting code are forbidden.

See ``docs/design/spec-driven-architecture.md`` §3.2 for the trust model and
the full allow/block-list rationale.

This module is internal to the v0.11 spec-driven layer.
"""

from __future__ import annotations

from specstar.validator.ast import (
    BLOCKED_BUILTINS,
    BLOCKED_IMPORTS,
    BLOCKED_STATEMENTS,
    SAFE_DUNDERS,
    DeclarativeASTValidator,
    ValidationError,
)

__all__ = [
    "BLOCKED_BUILTINS",
    "BLOCKED_IMPORTS",
    "BLOCKED_STATEMENTS",
    "SAFE_DUNDERS",
    "DeclarativeASTValidator",
    "ValidationError",
]
