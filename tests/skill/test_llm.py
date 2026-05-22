"""Tests for the LLM client interface and factory dispatcher.

Real LLM calls are not exercised here — those need API keys and network.
The litellm-backed call path is structurally tested but not invoked.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from specstar.skill.llm import LLMError, ProviderConfig, build_client


class _DummyResponse(BaseModel):
    answer: str


class TestProviderConfig:
    def test_minimal_construction(self) -> None:
        c = ProviderConfig(provider="anthropic", model="claude-sonnet-4-6")
        assert c.provider == "anthropic"
        assert c.model == "claude-sonnet-4-6"
        assert c.max_tokens == 8000
        assert c.max_retries == 3
        assert c.temperature == 0.0
        assert c.base_url is None
        assert c.api_key is None

    def test_self_host(self) -> None:
        c = ProviderConfig(
            provider="openai-compatible",
            model="llama3.1",
            base_url="http://localhost:11434/v1",
            api_key="ollama",
        )
        assert c.base_url == "http://localhost:11434/v1"
        assert c.api_key == "ollama"

    def test_overrides(self) -> None:
        c = ProviderConfig(
            provider="anthropic",
            model="claude-opus-4-7",
            max_tokens=16000,
            max_retries=5,
            temperature=0.7,
        )
        assert c.max_tokens == 16000
        assert c.max_retries == 5
        assert c.temperature == 0.7


class TestBuildClient:
    @pytest.mark.parametrize("provider", ["anthropic", "openai", "openai-compatible"])
    def test_supported_providers_dispatch(self, provider: str) -> None:
        c = ProviderConfig(provider=provider, model="any")
        client = build_client(c)
        # Same class for all three (LiteLLMClient); just verify it constructs.
        assert client is not None
        assert hasattr(client, "call")

    def test_unknown_provider_raises_value_error(self) -> None:
        c = ProviderConfig(provider="cohere", model="command")
        with pytest.raises(ValueError, match="unknown LLM provider"):
            build_client(c)

    def test_value_error_lists_supported_providers(self) -> None:
        c = ProviderConfig(provider="palm", model="text-bison")
        with pytest.raises(ValueError) as exc:
            build_client(c)
        msg = str(exc.value)
        assert "anthropic" in msg
        assert "openai" in msg


class TestLLMError:
    def test_default_not_retriable_no_cause(self) -> None:
        e = LLMError("oops")
        assert e.retriable is False
        assert e.cause is None
        assert str(e) == "oops"

    def test_with_retriable_and_cause(self) -> None:
        cause = RuntimeError("inner")
        e = LLMError("outer", retriable=True, cause=cause)
        assert e.retriable is True
        assert e.cause is cause


class TestLiteLLMClientStructure:
    """Structural tests on LiteLLMClient that don't invoke litellm."""

    def test_litellm_model_id_anthropic(self) -> None:
        from specstar.skill._litellm_impl import LiteLLMClient

        c = LiteLLMClient(
            ProviderConfig(provider="anthropic", model="claude-sonnet-4-6")
        )
        assert c._litellm_model_id() == "anthropic/claude-sonnet-4-6"

    def test_litellm_model_id_openai(self) -> None:
        from specstar.skill._litellm_impl import LiteLLMClient

        c = LiteLLMClient(ProviderConfig(provider="openai", model="gpt-4o"))
        assert c._litellm_model_id() == "openai/gpt-4o"

    def test_litellm_model_id_self_host(self) -> None:
        # OpenAI-compatible self-host uses "openai/<model>" + api_base
        from specstar.skill._litellm_impl import LiteLLMClient

        c = LiteLLMClient(
            ProviderConfig(
                provider="openai-compatible",
                model="llama3.1",
                base_url="http://localhost:11434/v1",
            )
        )
        assert c._litellm_model_id() == "openai/llama3.1"


class TestOpenAIStrictSchemaPatch:
    """Verify the OpenAI-strict schema rewriter."""

    def test_adds_additional_properties_false_to_top_object(self) -> None:
        from specstar.skill._litellm_impl import _make_openai_strict

        schema = {"type": "object", "properties": {"x": {"type": "string"}}}
        out = _make_openai_strict(schema)
        assert out["additionalProperties"] is False

    def test_adds_all_properties_to_required(self) -> None:
        from specstar.skill._litellm_impl import _make_openai_strict

        schema = {
            "type": "object",
            "properties": {
                "a": {"type": "string"},
                "b": {"type": "integer"},
                "c": {"type": "boolean"},
            },
        }
        out = _make_openai_strict(schema)
        assert sorted(out["required"]) == ["a", "b", "c"]

    def test_recurses_into_defs(self) -> None:
        from specstar.skill._litellm_impl import _make_openai_strict

        schema = {
            "type": "object",
            "properties": {"item": {"$ref": "#/$defs/Inner"}},
            "$defs": {
                "Inner": {
                    "type": "object",
                    "properties": {"y": {"type": "string"}},
                }
            },
        }
        out = _make_openai_strict(schema)
        assert out["$defs"]["Inner"]["additionalProperties"] is False
        assert out["$defs"]["Inner"]["required"] == ["y"]

    def test_recurses_into_array_items(self) -> None:
        from specstar.skill._litellm_impl import _make_openai_strict

        schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
            },
        }
        out = _make_openai_strict(schema)
        assert out["items"]["additionalProperties"] is False
        assert out["items"]["required"] == ["name"]

    def test_real_specplan_schema_becomes_openai_strict(self) -> None:
        """End-to-end: a real SpecPlan schema should become OpenAI-strict."""
        from specstar.skill._litellm_impl import _make_openai_strict
        from specstar.skill.schemas import SpecPlan

        schema = SpecPlan.model_json_schema()
        patched = _make_openai_strict(schema)
        # Top-level: every property in required, additionalProperties=false.
        assert patched["additionalProperties"] is False
        expected_props = {
            "reasoning",
            "summary",
            "resources",
            "inferred_decisions",
            "breaking_changes",
            "spec_md_after",
        }
        assert set(patched["required"]) == expected_props
        # Every nested $defs entry also patched.
        for defname, defschema in patched.get("$defs", {}).items():
            if "properties" in defschema:
                assert defschema["additionalProperties"] is False, (
                    f"{defname} missing additionalProperties=false"
                )

    def test_non_object_passes_through(self) -> None:
        from specstar.skill._litellm_impl import _make_openai_strict

        # Primitive schemas don't get touched.
        out = _make_openai_strict({"type": "string"})
        assert "additionalProperties" not in out
        assert "required" not in out

    def test_handles_anyof(self) -> None:
        from specstar.skill._litellm_impl import _make_openai_strict

        schema = {
            "anyOf": [
                {"type": "object", "properties": {"x": {"type": "string"}}},
                {"type": "null"},
            ]
        }
        out = _make_openai_strict(schema)
        assert out["anyOf"][0]["additionalProperties"] is False
        assert out["anyOf"][0]["required"] == ["x"]
