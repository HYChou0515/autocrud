"""LLM client interface and factory.

SpecStar's contract for invoking LLMs with structured output. The
underlying transport is pluggable; the default implementation in
``_litellm_impl.py`` uses litellm for broad provider coverage
(Anthropic, OpenAI, OpenAI-compatible self-host, Bedrock, Vertex,
Mistral, Gemini, ...).

The interface is deliberately narrow:

- Pass a system prompt + user message + Pydantic response model.
- The implementation handles JSON parsing, schema validation, and
  retry-on-validation-failure (feeding errors back to the LLM).
- The caller receives a typed Pydantic instance.

Implementations are imported lazily — if litellm (or any other backend)
is not installed, the import error becomes a clear LLMError at call
time, not at module load.
"""

from __future__ import annotations

from typing import Protocol, TypeVar

from msgspec import Struct
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ProviderConfig(Struct, frozen=True):
    """Resolved configuration for a single LLM call.

    Provider examples:

    - ``provider="anthropic"`` with ``model="claude-sonnet-4-6"``
    - ``provider="openai"`` with ``model="gpt-4o"``
    - ``provider="openai-compatible"`` with
      ``base_url="http://localhost:11434/v1"`` and ``model="llama3.1"``
      (Ollama, vLLM, LM Studio, llama.cpp server, ...)

    ``api_key`` is read from environment by the CLI layer
    (``ANTHROPIC_API_KEY``, ``OPENAI_API_KEY``, ...) and passed in here
    explicitly so the client doesn't reach for global state.
    """

    provider: str
    model: str
    base_url: str | None = None
    api_key: str | None = None
    max_tokens: int = 8000
    max_retries: int = 3
    """Schema-validation retries before giving up. Each retry feeds the
    Pydantic ValidationError back to the LLM."""

    temperature: float = 0.0


class LLMClient(Protocol):
    """Minimum contract for invoking an LLM with structured output.

    Implementations must:

    - call the LLM once or more with the given system + user prompts
    - coerce the response to ``response_model`` (the Pydantic class)
    - retry on validation failure up to ``ProviderConfig.max_retries``
    - raise :class:`LLMError` on any unrecoverable failure

    Implementations may add provider-specific features (streaming, prompt
    caching, tool use) but must not require them via the interface.
    """

    def call(
        self,
        *,
        system: str,
        user: str,
        response_model: type[T],
    ) -> T: ...


class LLMError(Exception):
    """SpecStar-owned error type for LLM call failures.

    Implementations wrap their own exceptions in this so callers can
    handle failures without importing provider SDKs.

    Attributes:
        retriable: Whether the caller can sensibly retry (e.g. rate-limit
            or transient network failure). Validation failures and auth
            errors are not retriable.
        cause: The original exception, if any, for diagnostic logging.
    """

    def __init__(
        self,
        message: str,
        *,
        retriable: bool = False,
        cause: Exception | None = None,
    ):
        super().__init__(message)
        self.retriable = retriable
        self.cause = cause


def build_client(config: ProviderConfig) -> LLMClient:
    """Build an :class:`LLMClient` for the given provider config.

    All currently-supported providers route through litellm (lazy
    imported). Override the dispatcher here if you add a non-litellm
    backend.
    """
    if config.provider in ("anthropic", "openai", "openai-compatible"):
        from specstar.skill._litellm_impl import LiteLLMClient

        return LiteLLMClient(config)
    raise ValueError(
        f"unknown LLM provider: {config.provider!r}. "
        "Supported: 'anthropic', 'openai', 'openai-compatible'."
    )
