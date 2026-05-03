"""Spec-driven authoring layer for SpecStar.

The two-step pipeline:

::

    intent.md  ──[STEP 1: prose → structured spec]──>  spec.md
    spec.md    ──[STEP 2: structured spec → Python]──>  <package>/_generated.py

Both steps are LLM-driven. The transport (litellm by default) is pluggable
via :mod:`specstar.skill.llm`. The structured outputs are typed via
:mod:`specstar.skill.schemas`.

This module is internal to the v0.11 spec-driven layer.
"""

from __future__ import annotations

from specstar.skill.llm import LLMClient, LLMError, ProviderConfig, build_client
from specstar.skill.prompts import (
    STEP1_SYSTEM_PROMPT,
    STEP2_SYSTEM_PROMPT,
    Step1Input,
    Step2Input,
    build_step1_messages,
    build_step1_user_prompt,
    build_step2_messages,
    build_step2_user_prompt,
)
from specstar.skill.schemas import (
    BreakingChange,
    FieldChange,
    InferredDecision,
    PythonPlan,
    ResourceChange,
    SpecPlan,
)

__all__ = [
    # llm
    "LLMClient",
    "LLMError",
    "ProviderConfig",
    "build_client",
    # prompts
    "STEP1_SYSTEM_PROMPT",
    "STEP2_SYSTEM_PROMPT",
    "Step1Input",
    "Step2Input",
    "build_step1_messages",
    "build_step1_user_prompt",
    "build_step2_messages",
    "build_step2_user_prompt",
    # schemas
    "BreakingChange",
    "FieldChange",
    "InferredDecision",
    "PythonPlan",
    "ResourceChange",
    "SpecPlan",
]
