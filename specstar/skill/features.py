"""Feature-toggle resolution for spec-driven codegen.

Decides which `add_model` kwargs the LLM is allowed to emit in
``_generated.py``. The resolved list is rendered into the STEP 2 user
prompt as an "Enabled features" preamble; the LLM is instructed to
generate code only for enabled features and leave disabled-feature
content as comments.

Resolution order: ``pyproject.toml [tool.specstar].features`` → CLI
overrides (``--feature`` / ``--no-feature``) → fallback default.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

DEFAULT_FEATURES: tuple[str, ...] = ("permissions", "workflows", "schema")
"""The conservative phase-1 default. Can be widened per-project via
``[tool.specstar].features = [...]`` once the corresponding codegen
slices ship."""


def resolve_features(
    *,
    pyproject_value: list[str] | None = None,
    cli_enable: list[str] | None = None,
    cli_disable: list[str] | None = None,
) -> tuple[str, ...]:
    """Return the list of feature names enabled for this gen run.

    ``pyproject_value`` is the value of ``[tool.specstar].features`` if
    that key was present in ``pyproject.toml`` (``None`` means the key
    is absent — fall back to :data:`DEFAULT_FEATURES`). An explicit
    empty list disables all features.

    ``cli_enable`` is the list of features added via ``--feature``.
    Idempotent: a feature already in the base is not duplicated.

    ``cli_disable`` is the list of features removed via
    ``--no-feature``. Silent when the feature isn't enabled.
    Disable beats enable when both reference the same feature.
    """
    if pyproject_value is None:
        result = list(DEFAULT_FEATURES)
    else:
        result = list(pyproject_value)
    if cli_enable:
        for feature in cli_enable:
            if feature not in result:
                result.append(feature)
    if cli_disable:
        for feature in cli_disable:
            if feature in result:
                result.remove(feature)
    return tuple(result)


def load_features_from_pyproject(path: Path) -> list[str] | None:
    """Read ``[tool.specstar].features`` from ``path`` (a pyproject.toml).

    Returns ``None`` when the file is missing or the key is absent —
    a key-absent signal that the caller forwards to
    :func:`resolve_features` so the framework default kicks in.
    Returns the (possibly empty) list when the key is present.
    """
    if not path.exists():
        return None
    with path.open("rb") as f:
        data = tomllib.load(f)
    tool = data.get("tool", {})
    specstar = tool.get("specstar", {})
    if "features" not in specstar:
        return None
    return list(specstar["features"])
