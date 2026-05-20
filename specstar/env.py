"""Thin env-var reader with lazy ``.env`` loading.

Why: spec-driven ``_generated.py`` is gated by an AST validator that
blocks ``import os``. ``specstar.env(...)`` is the sanctioned way for
declarative code to reference deployment secrets (DB URLs, S3 buckets,
etc.) without crossing into general-purpose ``os`` territory.

The first call also tries to load ``./.env`` (12-factor convention) so
dev workflows don't need to ``export X=Y`` before every run; in
production where env is already injected, the missing file is silent.
"""

from __future__ import annotations

import os
from pathlib import Path

_dotenv_loaded = False


def env(name: str, *, default: str | None = None) -> str:
    """Return ``os.environ[name]``, loading ``./.env`` once if needed.

    First call also reads ``./.env`` into ``os.environ`` so dev
    workflows don't need to ``export X=Y`` before every run. The
    dotenv file does NOT override existing env vars — production
    container env always wins.
    """
    global _dotenv_loaded
    if not _dotenv_loaded:
        _dotenv_loaded = True
        _load_dotenv_if_present(Path(".env"))
    if name in os.environ:
        return os.environ[name]
    if default is not None:
        return default
    raise KeyError(name)


def cache_clear() -> None:
    """Reset internal state. Used by tests that re-stage ``.env``."""
    global _dotenv_loaded
    _dotenv_loaded = False


env.cache_clear = cache_clear  # type: ignore[attr-defined]


def _load_dotenv_if_present(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())
