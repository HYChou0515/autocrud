"""Benchmark configuration loader and validation.

Reads a YAML configuration file, expands ``${ENV_VAR}`` placeholders, and
validates the resulting structure into typed dataclasses.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_MODELS = {"simple", "nested", "complex", "with_binary"}
VALID_ENCODINGS = {"json", "msgpack"}
VALID_OPERATIONS = {
    "create",
    "get",
    "update",
    "delete",
    "search",
    "patch",
    "modify",
    "switch",
    "restore",
    "list_resources",
}
VALID_STORAGES = {"memory", "disk", "postgres", "s3", "pg_disk"}

_ENV_RE = re.compile(r"\$\{(\w+)\}")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class StorageConfig:
    """Configuration for a single storage backend."""

    name: str
    params: dict[str, Any] = field(default_factory=dict)
    available: bool = True
    unavailable_reason: str = ""


@dataclass
class ScenarioConfig:
    """Configuration for a single benchmark scenario."""

    name: str
    storage: str
    encoding: str
    model: str
    operations: list[str]
    n: int | None = None
    warmup: int | None = None
    repeat: int | None = None


@dataclass
class BenchmarkConfig:
    """Top-level benchmark configuration."""

    output_dir: str = "benchmark/results"
    default_n: int = 1000
    default_warmup: int = 10
    default_repeat: int = 3
    models: list[str] = field(default_factory=lambda: list(VALID_MODELS))
    storage: dict[str, StorageConfig] = field(default_factory=dict)
    scenarios: list[ScenarioConfig] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _expand_env(value: Any) -> tuple[Any, list[str]]:
    """Expand ``${VAR}`` placeholders in *value*.

    Returns the expanded value and a list of missing env-var names.
    """
    if isinstance(value, str):
        missing: list[str] = []

        def _replace(m: re.Match) -> str:
            var = m.group(1)
            env_val = os.environ.get(var)
            if env_val is None:
                missing.append(var)
                return m.group(0)  # keep original placeholder
            return env_val

        expanded = _ENV_RE.sub(_replace, value)
        return expanded, missing

    if isinstance(value, dict):
        all_missing: list[str] = []
        out: dict[str, Any] = {}
        for k, v in value.items():
            ev, m = _expand_env(v)
            out[k] = ev
            all_missing.extend(m)
        return out, all_missing

    if isinstance(value, list):
        all_missing = []
        out_list: list[Any] = []
        for v in value:
            ev, m = _expand_env(v)
            out_list.append(ev)
            all_missing.extend(m)
        return out_list, all_missing

    return value, []


def _parse_storage(name: str, raw: Any) -> StorageConfig:
    """Parse a single storage entry from the YAML dict."""
    params = raw if isinstance(raw, dict) else {}
    expanded, missing = _expand_env(params)
    if missing:
        return StorageConfig(
            name=name,
            params=expanded,
            available=False,
            unavailable_reason=f"Missing env vars: {', '.join(missing)}",
        )
    return StorageConfig(name=name, params=expanded, available=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(path: str | Path) -> BenchmarkConfig:
    """Load and validate a benchmark YAML configuration file.

    Args:
        path: Path to the YAML config file.

    Returns:
        A validated :class:`BenchmarkConfig` instance.

    Raises:
        FileNotFoundError: If *path* does not exist.
        ValueError: If validation fails.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError("Config must be a YAML mapping at the top level.")

    # --- storage ---
    storage_map: dict[str, StorageConfig] = {}
    for sname, sparams in (raw.get("storage") or {}).items():
        if sname not in VALID_STORAGES:
            raise ValueError(
                f"Unknown storage '{sname}'. Valid: {sorted(VALID_STORAGES)}"
            )
        storage_map[sname] = _parse_storage(sname, sparams)

    # --- scenarios ---
    scenarios: list[ScenarioConfig] = []
    for idx, s in enumerate(raw.get("scenarios") or []):
        if not isinstance(s, dict):
            raise ValueError(f"Scenario #{idx} must be a mapping.")
        name = s.get("name", f"scenario-{idx}")

        storage_name = s.get("storage", "")
        if storage_name not in VALID_STORAGES:
            raise ValueError(
                f"Scenario '{name}': unknown storage '{storage_name}'. "
                f"Valid: {sorted(VALID_STORAGES)}"
            )
        if storage_name not in storage_map:
            raise ValueError(
                f"Scenario '{name}': storage '{storage_name}' not defined "
                f"in the storage section."
            )

        encoding = s.get("encoding", "json")
        if encoding not in VALID_ENCODINGS:
            raise ValueError(
                f"Scenario '{name}': unknown encoding '{encoding}'. "
                f"Valid: {sorted(VALID_ENCODINGS)}"
            )

        model = s.get("model", "simple")
        if model not in VALID_MODELS:
            raise ValueError(
                f"Scenario '{name}': unknown model '{model}'. "
                f"Valid: {sorted(VALID_MODELS)}"
            )

        ops = s.get("operations", [])
        invalid_ops = set(ops) - VALID_OPERATIONS
        if invalid_ops:
            raise ValueError(
                f"Scenario '{name}': unknown operations {sorted(invalid_ops)}. "
                f"Valid: {sorted(VALID_OPERATIONS)}"
            )

        scenarios.append(
            ScenarioConfig(
                name=name,
                storage=storage_name,
                encoding=encoding,
                model=model,
                operations=ops,
                n=s.get("n"),
                warmup=s.get("warmup"),
                repeat=s.get("repeat"),
            )
        )

    # --- models list ---
    models_list = raw.get("models") or list(VALID_MODELS)
    if isinstance(models_list, list):
        invalid_models = set(models_list) - VALID_MODELS
        if invalid_models:
            raise ValueError(
                f"Unknown models: {sorted(invalid_models)}. "
                f"Valid: {sorted(VALID_MODELS)}"
            )
    else:
        models_list = list(VALID_MODELS)

    return BenchmarkConfig(
        output_dir=raw.get("output_dir", "benchmark/results"),
        default_n=int(raw.get("default_n", 1000)),
        default_warmup=int(raw.get("default_warmup", 10)),
        default_repeat=int(raw.get("default_repeat", 3)),
        models=models_list,
        storage=storage_map,
        scenarios=scenarios,
    )
