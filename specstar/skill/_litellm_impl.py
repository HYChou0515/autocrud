"""litellm-backed :class:`LLMClient` implementation.

Internal — not for direct import. Use
:func:`specstar.skill.llm.build_client` to obtain a client.

Why litellm: provider coverage. SpecStar's mission is "spec-driven, not
LLM-locked", and litellm reaches 100+ providers (Anthropic, OpenAI,
Bedrock, Vertex, Mistral, Gemini, Cohere, Ollama, vLLM, LM Studio, ...)
through one API. The trade-off vs higher-level libraries (instructor,
Pydantic AI) is that litellm doesn't auto-retry on schema validation —
we implement that here in ~30 lines.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from specstar.skill.llm import LLMError, ProviderConfig


def _make_openai_strict(schema: Any) -> Any:
    """Patch a JSON schema in place to satisfy OpenAI strict structured outputs.

    OpenAI's ``response_format={"strict": True}`` requires every object
    schema to have ``additionalProperties: false`` and every property to
    appear in the ``required`` list, even those Pydantic considers
    optional (i.e. with default values).

    Recurses through ``properties``, ``$defs`` / ``definitions``,
    ``items``, and ``anyOf`` / ``oneOf`` / ``allOf``.

    Anthropic and most self-hosted providers do not have this
    requirement; the patch is gated on provider in :class:`LiteLLMClient`.
    """
    if not isinstance(schema, dict):
        return schema

    is_object = schema.get("type") == "object" or "properties" in schema
    if is_object:
        schema["additionalProperties"] = False
        if "properties" in schema:
            schema["required"] = list(schema["properties"].keys())

    if "properties" in schema:
        for v in schema["properties"].values():
            _make_openai_strict(v)
    for key in ("$defs", "definitions"):
        if key in schema:
            for v in schema[key].values():
                _make_openai_strict(v)
    if "items" in schema:
        _make_openai_strict(schema["items"])
    for key in ("anyOf", "oneOf", "allOf"):
        if key in schema:
            for v in schema[key]:
                _make_openai_strict(v)

    return schema


class LiteLLMClient:
    """LLMClient using litellm as transport.

    Implements the validation-retry loop ourselves: on Pydantic
    ValidationError, we feed the error back to the LLM as a follow-up
    user message and retry up to ``config.max_retries`` times.
    """

    def __init__(self, config: ProviderConfig):
        self._config = config

    def call(self, *, system, user, response_model):
        try:
            import litellm
            import pydantic
        except ImportError as e:  # pragma: no cover - import guard
            raise LLMError(
                "litellm is not installed. Install with: pip install 'specstar[gen]'",
                retriable=False,
                cause=e,
            )

        schema_json = response_model.model_json_schema()
        # OpenAI's strict structured-outputs has stricter requirements than
        # Pydantic emits by default. Patch the schema only for OpenAI-family
        # providers; Anthropic accepts the original.
        if self._config.provider in ("openai", "openai-compatible"):
            schema_json = _make_openai_strict(deepcopy(schema_json))
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        last_text = ""

        for _attempt in range(self._config.max_retries):
            try:
                resp = litellm.completion(
                    model=self._litellm_model_id(),
                    messages=messages,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": response_model.__name__,
                            "schema": schema_json,
                            "strict": True,
                        },
                    },
                    max_tokens=self._config.max_tokens,
                    temperature=self._config.temperature,
                    api_key=self._config.api_key,
                    api_base=self._config.base_url,
                )
            except Exception as e:
                # litellm's exception classes are version-dependent. Catch
                # broad and let LLMError carry the original for callers that
                # need to discriminate.
                exc_name = type(e).__name__.lower()
                retriable = any(
                    keyword in exc_name
                    for keyword in ("ratelimit", "timeout", "service")
                )
                raise LLMError(str(e), retriable=retriable, cause=e) from e

            last_text = resp.choices[0].message.content or ""
            try:
                return response_model.model_validate_json(last_text)
            except pydantic.ValidationError as ve:
                # Self-correction: feed the Pydantic error back to the LLM.
                messages.extend(
                    [
                        {"role": "assistant", "content": last_text},
                        {
                            "role": "user",
                            "content": (
                                "Your previous response failed schema "
                                f"validation:\n{ve}\n\n"
                                "Re-emit a response that conforms exactly "
                                "to the JSON schema."
                            ),
                        },
                    ]
                )

        raise LLMError(
            f"schema validation failed after {self._config.max_retries} attempts; "
            f"last raw response (first 500 chars): {last_text[:500]}",
            retriable=False,
        )

    def _litellm_model_id(self) -> str:
        """Map ``(provider, model)`` to litellm's model id format.

        - ``"anthropic/claude-sonnet-4-6"``
        - ``"openai/gpt-4o"``
        - For OpenAI-compatible self-host: ``"openai/<model>"`` with
          ``api_base`` pointing at the local server.
        """
        if self._config.provider == "openai-compatible":
            return f"openai/{self._config.model}"
        return f"{self._config.provider}/{self._config.model}"
