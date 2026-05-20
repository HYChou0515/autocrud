"""Tests for ``specstar.env`` — a thin env-var reader with lazy
``.env`` loading.

Used by spec-driven codegen so ``_generated.py`` can write
``Postgres(database_url=specstar.env("DATABASE_URL"))`` without
importing ``os`` (which is on the AST validator's blocklist for
declarative ``_generated.py``).
"""

from __future__ import annotations

import specstar


from pathlib import Path

import pytest


def test_returns_value_from_existing_os_environ(monkeypatch) -> None:
    # Tracer: when the var is already set in os.environ, specstar.env
    # returns it verbatim.
    monkeypatch.setenv("SPECSTAR_TEST_VAR", "live-value")
    assert specstar.env("SPECSTAR_TEST_VAR") == "live-value"


def test_loads_from_dotenv_when_var_missing(monkeypatch, tmp_path: Path) -> None:
    # When ./.env exists and the var is NOT in os.environ, specstar.env
    # must parse the dotenv file and return the value.
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SPECSTAR_FROM_DOTENV", raising=False)
    (tmp_path / ".env").write_text(
        "SPECSTAR_FROM_DOTENV=dotenv-value\n", encoding="utf-8"
    )
    specstar.env.cache_clear()  # type: ignore[attr-defined]
    assert specstar.env("SPECSTAR_FROM_DOTENV") == "dotenv-value"


def test_real_env_wins_over_dotenv(monkeypatch, tmp_path: Path) -> None:
    # 12-factor: prod env (container / k8s / docker) wins. .env is a
    # dev-only fallback; it must NOT clobber a value that was set in
    # the real process env.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SPECSTAR_OVERRIDE_TEST", "from-real-env")
    (tmp_path / ".env").write_text(
        "SPECSTAR_OVERRIDE_TEST=from-dotenv\n", encoding="utf-8"
    )
    specstar.env.cache_clear()  # type: ignore[attr-defined]
    assert specstar.env("SPECSTAR_OVERRIDE_TEST") == "from-real-env"


def test_missing_var_with_no_default_raises_key_error(monkeypatch) -> None:
    # Required-but-missing env vars must fail loud — silent default of
    # empty string would let prod start with a broken DB URL.
    monkeypatch.delenv("SPECSTAR_NO_SUCH_VAR", raising=False)
    with pytest.raises(KeyError, match="SPECSTAR_NO_SUCH_VAR"):
        specstar.env("SPECSTAR_NO_SUCH_VAR")


def test_default_returned_when_var_missing(monkeypatch) -> None:
    # Explicit default → graceful fallback (e.g. port=8000 when unset).
    monkeypatch.delenv("SPECSTAR_NO_SUCH_VAR_WITH_DEFAULT", raising=False)
    assert (
        specstar.env("SPECSTAR_NO_SUCH_VAR_WITH_DEFAULT", default="fallback")
        == "fallback"
    )
