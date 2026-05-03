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
