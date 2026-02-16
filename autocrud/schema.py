"""Schema: unified migration + validation for AutoCRUD resources.

``Schema`` replaces the separate ``IMigration`` / ``IValidator`` interfaces
with a single fluent API that supports:

* **Chain migration** via ``.step()`` — sequential transforms with auto-inferred
  target versions.
* **Parallel chains** via ``.plus()`` — alternative migration paths that start
  new chains (BFS finds shortest path at runtime).
* **Validation** — optional callable / ``IValidator`` / Pydantic model attached
  once and re-used on every write.
* **Reindex-only** — ``Schema("v2")`` with no steps triggers a version bump +
  re-index without data transformation.

Backward compatibility
~~~~~~~~~~~~~~~~~~~~~~
``Schema`` exposes ``.schema_version`` and ``.migrate()`` matching the legacy
``IMigration`` protocol so that ``ResourceManager`` can treat it identically.
``Schema.from_legacy(migration)`` wraps an existing ``IMigration`` instance.
"""

from __future__ import annotations

import io
from collections import defaultdict, deque
from typing import IO, Any, Callable, Generic, TypeVar

from autocrud.resource_manager.pydantic_converter import build_validator

T = TypeVar("T")


class Schema(Generic[T]):
    """Unified migration + validation descriptor.

    Parameters
    ----------
    version : str | None
        The **target** schema version.  ``None`` means "no versioning".
    validator : Callable | IValidator | type | None
        Optional validator (same types accepted by the old ``validator=``
        parameter on ``add_model``).

    Examples
    --------
    Simple reindex (version bump, no data change)::

        Schema("v2")

    Single-step migration::

        Schema("v2").step("v1", migrate_v1_to_v2)

    Chain migration with auto-inferred ``to``::

        Schema("v3").step("v1", fn1).step("v2", fn2)
        # fn1: v1 → v2  (inferred from next step's from_ver)
        # fn2: v2 → v3  (inferred from Schema target version)

    Parallel paths::

        Schema("v3").step("v1", fn1).step("v2", fn2).plus("v1", fn_shortcut)
        # fn_shortcut: v1 → v3  (last in chain, inferred from target)

    With validation::

        Schema("v2", validator=my_validator).step("v1", fn)
    """

    def __init__(
        self,
        version: str | None = None,
        validator: "Callable | Any | None" = None,
    ):
        self._version = version
        self._raw_validator = validator
        self._validator: Callable | None = build_validator(validator)
        # List of flushed chains.  Each chain is a list of (from_ver, fn) tuples
        # whose ``to`` will be resolved lazily.
        self._chains: list[list[tuple[str, Callable[[IO[bytes]], Any]]]] = []
        # The chain currently being built (not yet flushed).
        self._current_chain: list[tuple[str, Callable[[IO[bytes]], Any]]] = []
        # Explicit ``to`` overrides: {chain_idx: {step_idx: to_ver}}
        self._explicit_to: dict[int, dict[int, str]] = {}
        # Resolved directed graph cache (invalidated on mutation).
        self._graph: dict[str, list[tuple[str, Callable[[IO[bytes]], Any]]]] | None = (
            None
        )
        # Legacy migration wrapper (set by ``from_legacy``).
        self._legacy_migration: Any = None

    # ------------------------------------------------------------------
    # Fluent builders
    # ------------------------------------------------------------------

    def step(
        self,
        from_ver: str,
        fn: Callable[[IO[bytes]], Any],
        *,
        to: str | None = None,
    ) -> Schema[T]:
        """Append a migration step to the *current* chain.

        Parameters
        ----------
        from_ver : str
            Source version that this step handles.
        fn : Callable[[IO[bytes]], Any]
            Transform function ``(data_stream) -> migrated_object``.
        to : str | None
            Explicit target version.  If ``None`` it is auto-inferred:
            * Middle step → next step's ``from_ver``.
            * Last step in a chain → ``Schema.version``.
        """
        self._current_chain.append((from_ver, fn))
        if to is not None:
            chain_idx = len(self._chains)  # current chain's future index
            step_idx = len(self._current_chain) - 1
            self._explicit_to.setdefault(chain_idx, {})[step_idx] = to
        self._graph = None  # invalidate cache
        return self

    def plus(
        self,
        from_ver: str,
        fn: Callable[[IO[bytes]], Any],
        *,
        to: str | None = None,
    ) -> Schema[T]:
        """Start a **new** parallel chain with the given first step.

        Same semantics as ``.step()`` but the previous chain is flushed first
        so that its ``to`` versions get resolved independently.
        """
        # Flush current chain
        if self._current_chain:
            self._chains.append(self._current_chain)
            self._current_chain = []
        # ``.step()`` will use ``len(self._chains)`` as chain_idx for the new
        # chain that is being started.
        return self.step(from_ver, fn, to=to)

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def _resolve(self) -> dict[str, list[tuple[str, Callable[[IO[bytes]], Any]]]]:
        """Lazily resolve all chains into a directed graph."""
        if self._graph is not None:
            return self._graph

        # Collect all chains (include current if non-empty).
        all_chains: list[list[tuple[str, Callable[[IO[bytes]], Any]]]] = list(
            self._chains
        )
        if self._current_chain:
            all_chains.append(self._current_chain)

        graph: dict[str, list[tuple[str, Callable[[IO[bytes]], Any]]]] = defaultdict(
            list
        )

        for chain_idx, chain in enumerate(all_chains):
            chain_explicit = self._explicit_to.get(chain_idx, {})
            for i, (from_ver, fn) in enumerate(chain):
                # Determine ``to_ver``
                if i in chain_explicit:
                    to_ver = chain_explicit[i]
                elif i + 1 < len(chain):
                    to_ver = chain[i + 1][0]
                else:
                    # Last step in chain → target is ``Schema.version``
                    to_ver = self._version
                if to_ver is None:
                    raise ValueError(
                        f"Cannot infer target version for step from {from_ver!r}. "
                        f"Set Schema(version=...) or provide to= explicitly."
                    )
                graph[from_ver].append((to_ver, fn))

        self._graph = dict(graph)
        return self._graph

    # ------------------------------------------------------------------
    # Path finding (BFS shortest path)
    # ------------------------------------------------------------------

    def _find_path(
        self, from_ver: str | None, to_ver: str
    ) -> list[tuple[str, str, Callable[[IO[bytes]], Any]]]:
        """Find shortest path from *from_ver* to *to_ver* via BFS.

        Returns list of ``(src, dst, fn)`` tuples forming the path.

        Raises ``ValueError`` if no path exists.
        """
        graph = self._resolve()

        if from_ver == to_ver:
            return []

        if from_ver not in graph:
            raise ValueError(
                f"No migration path from version {from_ver!r} to {to_ver!r}. "
                f"Available source versions: {sorted(graph.keys())}"
            )

        # BFS
        queue: deque[list[tuple[str, str, Callable[[IO[bytes]], Any]]]] = deque()
        visited: set[str | None] = {from_ver}

        for dst, fn in graph.get(from_ver, []):
            queue.append([(from_ver, dst, fn)])
            visited.add(dst)

        while queue:
            path = queue.popleft()
            current = path[-1][1]  # last destination
            if current == to_ver:
                return path
            for dst, fn in graph.get(current, []):
                if dst not in visited:
                    visited.add(dst)
                    queue.append([*path, (current, dst, fn)])

        raise ValueError(
            f"No migration path from {from_ver!r} to {to_ver!r}. "
            f"Available edges: { {k: [t for t, _ in v] for k, v in graph.items()} }"
        )

    # ------------------------------------------------------------------
    # IMigration-compatible interface
    # ------------------------------------------------------------------

    @property
    def schema_version(self) -> str | None:
        """Target schema version (``IMigration`` compat)."""
        return self._version

    def migrate(self, data: IO[bytes], schema_version: str | None) -> T:
        """Migrate *data* from *schema_version* to the target version.

        If a legacy ``IMigration`` is wrapped, delegates to it directly.
        Otherwise uses graph-based BFS path finding and executes the
        transform chain.

        Compatible with the ``IMigration.migrate()`` signature so that
        ``ResourceManager`` can use ``Schema`` as a drop-in replacement.
        """
        # Legacy delegation
        if self._legacy_migration is not None:
            return self._legacy_migration.migrate(data, schema_version)

        target = self._version
        if target is None:
            raise ValueError("Schema has no target version; cannot migrate.")

        if schema_version == target:
            # Already at target — return raw bytes for caller to decode.
            return data.read()  # type: ignore[return-value]

        path = self._find_path(schema_version, target)
        if not path:
            return data.read()  # type: ignore[return-value]

        result: Any = data
        for _src, _dst, fn in path:
            if not isinstance(result, (io.IOBase, io.BufferedIOBase)):
                # Wrap intermediate results back into a stream for the next step
                if isinstance(result, bytes):
                    result = io.BytesIO(result)
                else:
                    # The previous fn returned a decoded object — we need to
                    # re-serialize so the next fn gets IO[bytes].
                    import msgspec

                    result = io.BytesIO(msgspec.json.encode(result))
            result = fn(result)

        return result  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, data: Any) -> None:
        """Run the attached validator, if any."""
        if self._validator is not None:
            from autocrud.types import ValidationError

            try:
                self._validator(data)
            except ValidationError:
                raise
            except Exception as e:
                raise ValidationError(str(e)) from e

    @property
    def has_validator(self) -> bool:
        """Whether a validator is attached."""
        return self._validator is not None

    @property
    def raw_validator(self) -> Callable | Any | None:
        """The original validator argument (before normalization)."""
        return self._raw_validator

    # ------------------------------------------------------------------
    # Legacy adapter
    # ------------------------------------------------------------------

    @classmethod
    def from_legacy(cls, migration: Any) -> Schema[T]:
        """Wrap an existing ``IMigration`` instance as a ``Schema``.

        The resulting ``Schema`` delegates ``.migrate()`` calls directly
        to the wrapped ``IMigration``.
        """
        from autocrud.types import IMigration

        if not isinstance(migration, IMigration):
            raise TypeError(
                f"Expected IMigration instance, got {type(migration).__name__}"
            )

        schema: Schema[T] = cls(version=migration.schema_version)
        schema._legacy_migration = migration
        return schema

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def has_migration(self) -> bool:
        """Whether this schema defines any migration steps (or wraps legacy)."""
        if self._legacy_migration is not None:
            return True
        return bool(self._current_chain or self._chains)

    @property
    def version(self) -> str | None:
        """The target schema version."""
        return self._version

    def __repr__(self) -> str:
        parts = [f"Schema({self._version!r}"]
        if self._validator is not None:
            parts[0] += ", validator=..."
        parts[0] += ")"
        all_chains: list[list[tuple[str, Callable[[IO[bytes]], Any]]]] = list(
            self._chains
        )
        if self._current_chain:
            all_chains.append(self._current_chain)
        for chain_idx, chain in enumerate(all_chains):
            for step_idx, (from_ver, _fn) in enumerate(chain):
                if chain_idx > 0 and step_idx == 0:
                    method = ".plus"
                else:
                    method = ".step"
                parts.append(f"{method}({from_ver!r}, ...)")
        return "".join(parts)
