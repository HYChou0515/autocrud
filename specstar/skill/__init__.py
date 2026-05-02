"""Prompt-engineering primitives shared by the Claude Code skill and the
``specstar gen`` CLI.

The Claude Code skill ships as ``.claude/skills/specstar-spec/SKILL.md``
(human-readable instructions). The ``specstar gen`` CLI calls Anthropic's
API directly with a system prompt + user message constructed by this
module. Both surfaces use the **same** rules — this module is the
single source of truth for the wording.

This module is internal to the v0.11 spec-driven layer.
"""

from __future__ import annotations

from specstar.skill.prompts import (
    AuthoringState,
    build_messages,
    build_system_prompt,
    build_user_prompt,
)

__all__ = [
    "AuthoringState",
    "build_messages",
    "build_system_prompt",
    "build_user_prompt",
]
