"""Schema: unified migration + validation for AutoCRUD resources.

``Schema`` bundles a **resource type**, **version**, optional **validator**,
and migration steps into a single fluent API that supports:

* **Chain migration** via ``.step()`` — sequential transforms with auto-inferred
  target versions.
* **Parallel chains** via ``.plus()`` — alternative migration paths that start
  new chains (BFS finds shortest path at runtime).
* **Validation** — optional callable / ``IValidator`` / Pydantic model attached
  once and re-used on every write.
* **Reindex-only** — ``Schema(MyModel, "v2")`` with no steps triggers a version
  bump + re-index without data transformation.

Backward compatibility
~~~~~~~~~~~~~~~~~~~~~~
``Schema`` exposes ``.schema_version`` and ``.migrate()`` matching the legacy
``IMigration`` protocol so that ``ResourceManager`` can treat it identically.
``Schema.from_legacy(migration)`` wraps an existing ``IMigration`` instance.
"""

from __future__ import annotations

import io
import re
from collections import defaultdict, deque
from typing import IO, Any, Callable, Generic, TypeVar

import msgspec

from autocrud.resource_manager.pydantic_converter import (
    build_validator,
    pydantic_to_dict,
)
from autocrud.types import IMigration

T = TypeVar("T")


class Schema(Generic[T]):
    """Unified migration + validation descriptor.

    Parameters
    ----------
    resource_type : type[T]
        The data model class (msgspec Struct or Pydantic BaseModel).
    version : str
        The **target** schema version.
    validator : Callable | IValidator | type | None
        Optional validator (same types accepted by the old ``validator=``
        parameter on ``add_model``).

    Examples
    --------
    Simple reindex (version bump, no data change)::

        Schema(User, "v2")

    Single-step migration::

        Schema(User, "v2").step("v1", migrate_v1_to_v2)

    Chain migration with auto-inferred ``to``::

        Schema(User, "v3").step("v1", fn1).step("v2", fn2)
        # fn1: v1 → v2  (inferred from next step's from_ver)
        # fn2: v2 → v3  (inferred from Schema target version)

    Parallel paths::

        Schema(User, "v3").step("v1", fn1).step("v2", fn2).plus("v1", fn_shortcut)
        # fn_shortcut: v1 → v3  (last in chain, inferred from target)

    With validation::

        Schema(User, "v2", validator=my_validator).step("v1", fn)
    """

    def __init__(
        self,
        resource_type: type[T],
        version: str,
        *,
        validator: "Callable | Any | None" = None,
    ):
        self._resource_type: type[T] = resource_type
        self._version: str = version
        self._raw_validator = validator
        self._validator: Callable | None = build_validator(validator)
        # List of flushed chains.  Each chain is a list of (from_ver, fn) tuples
        # whose ``to`` will be resolved lazily.
        # ``from_ver`` can be a plain string or a compiled regex pattern.
        self._chains: list[
            list[tuple[str | re.Pattern[str], Callable[[IO[bytes]], Any]]]
        ] = []
        # The chain currently being built (not yet flushed).
        self._current_chain: list[
            tuple[str | re.Pattern[str], Callable[[IO[bytes]], Any]]
        ] = []
        # Explicit ``to`` overrides: {chain_idx: {step_idx: to_ver}}
        self._explicit_to: dict[int, dict[int, str]] = {}
        # Resolved directed graph cache (invalidated on mutation).
        self._graph: dict[str, list[tuple[str, Callable[[IO[bytes]], Any]]]] | None = (
            None
        )
        # Regex edges resolved at build time but expanded at runtime.
        self._regex_edges: list[
            tuple[re.Pattern[str], str, Callable[[IO[bytes]], Any]]
        ] = []
        # Path cache: (from_ver, to_ver) → path.  Cleared on mutation.
        self._path_cache: dict[
            tuple[str | None, str],
            list[tuple[str, str, Callable[[IO[bytes]], Any]]],
        ] = {}
        # Legacy migration wrapper (set by ``from_legacy``).
        self._legacy_migration: IMigration | None = None
        # Encoder for re-serializing intermediate migration results.
        self._encoder = msgspec.json.Encoder()

    # ------------------------------------------------------------------
    # Fluent builders
    # ------------------------------------------------------------------

    def step(
        self,
        from_ver: str | re.Pattern[str],
        fn: Callable[[IO[bytes]], Any],
        *,
        to: str | None = None,
    ) -> Schema[T]:
        """Append a migration step to the *current* chain.

        Parameters
        ----------
        from_ver : str | re.Pattern[str]
            Source version that this step handles.  Can be a compiled regex
            pattern (``re.compile(...)``), in which case the step creates
            edges from **every** known version that matches the pattern.
        fn : Callable[[IO[bytes]], Any]
            Transform function ``(data_stream) -> migrated_object``.
        to : str | None
            Explicit target version.  If ``None`` it is auto-inferred:
            * Middle step → next step's ``from_ver`` (must be a literal string).
            * Last step in a chain → ``Schema.version``.
        """
        self._current_chain.append((from_ver, fn))
        if to is not None:
            chain_idx = len(self._chains)  # current chain's future index
            step_idx = len(self._current_chain) - 1
            self._explicit_to.setdefault(chain_idx, {})[step_idx] = to
        self._graph = None  # invalidate cache
        self._regex_edges = []
        self._path_cache = {}
        return self

    def plus(
        self,
        from_ver: str | re.Pattern[str],
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
        """Lazily resolve all chains into a directed graph.

        Literal ``from_ver`` strings are placed directly into the graph.
        Regex ``from_ver`` patterns are stored separately in
        ``_regex_edges`` and expanded at **runtime** (inside
        ``_edges_for``) so that they can match versions from the
        persistence layer that are not known at definition time.
        """
        if self._graph is not None:
            return self._graph

        # Collect all chains (include current if non-empty).
        all_chains: list[
            list[tuple[str | re.Pattern[str], Callable[[IO[bytes]], Any]]]
        ] = list(self._chains)
        if self._current_chain:
            all_chains.append(self._current_chain)

        # ── Pass 1: resolve to_ver for every step ─────────────────────
        resolved_steps: list[
            tuple[str | re.Pattern[str], str, Callable[[IO[bytes]], Any]]
        ] = []

        for chain_idx, chain in enumerate(all_chains):
            chain_explicit = self._explicit_to.get(chain_idx, {})
            for i, (from_ver, fn) in enumerate(chain):
                # Determine ``to_ver``
                if i in chain_explicit:
                    to_ver: str | None = chain_explicit[i]
                elif i + 1 < len(chain):
                    next_from = chain[i + 1][0]
                    if isinstance(next_from, re.Pattern):
                        raise ValueError(
                            f"Cannot infer target version for step from {from_ver!r} "
                            f"because the next step uses a regex pattern. "
                            f"Use explicit to= parameter."
                        )
                    to_ver = next_from
                else:
                    # Last step in chain → target is ``Schema.version``
                    to_ver = self._version
                if to_ver is None:
                    raise ValueError(
                        f"Cannot infer target version for step from {from_ver!r}. "
                        f"Set Schema(version=...) or provide to= explicitly."
                    )
                resolved_steps.append((from_ver, to_ver, fn))

        # ── Pass 2: separate literal edges vs regex edges ─────────────
        graph: dict[str, list[tuple[str, Callable[[IO[bytes]], Any]]]] = defaultdict(
            list
        )
        regex_edges: list[tuple[re.Pattern[str], str, Callable[[IO[bytes]], Any]]] = []

        for from_ver, to_ver, fn in resolved_steps:
            if isinstance(from_ver, re.Pattern):
                regex_edges.append((from_ver, to_ver, fn))
            else:
                graph[from_ver].append((to_ver, fn))

        self._graph = dict(graph)
        self._regex_edges = regex_edges
        return self._graph

    # ------------------------------------------------------------------
    # Runtime edge lookup
    # ------------------------------------------------------------------

    def _edges_for(self, version: str) -> list[tuple[str, Callable[[IO[bytes]], Any]]]:
        """Return outgoing edges for *version* (literal + regex matches).

        Called at runtime so that regex patterns can match versions from
        the persistence layer that were never declared in the Schema.
        """
        self._resolve()
        edges = list(self._graph.get(version, []))
        for pattern, to_ver, fn in self._regex_edges:
            if version != to_ver and pattern.fullmatch(version):
                edges.append((to_ver, fn))
        return edges

    # ------------------------------------------------------------------
    # Path finding (BFS shortest path)
    # ------------------------------------------------------------------

    def _find_path(
        self, from_ver: str | None, to_ver: str
    ) -> list[tuple[str, str, Callable[[IO[bytes]], Any]]]:
        """Find shortest path from *from_ver* to *to_ver* via BFS.

        Returns list of ``(src, dst, fn)`` tuples forming the path.
        Results are cached per ``(from_ver, to_ver)`` pair.

        Raises ``ValueError`` if no path exists.
        """
        self._resolve()

        if from_ver == to_ver:
            return []

        cache_key = (from_ver, to_ver)
        if cache_key in self._path_cache:
            return self._path_cache[cache_key]

        initial_edges = self._edges_for(from_ver)  # type: ignore[arg-type]
        if not initial_edges:
            raise ValueError(
                f"No migration path from version {from_ver!r} to {to_ver!r}. "
                f"No outgoing edges for {from_ver!r}."
            )

        # BFS
        queue: deque[list[tuple[str, str, Callable[[IO[bytes]], Any]]]] = deque()
        visited: set[str | None] = {from_ver}

        for dst, fn in initial_edges:
            queue.append([(from_ver, dst, fn)])
            visited.add(dst)

        while queue:
            path = queue.popleft()
            current = path[-1][1]  # last destination
            if current == to_ver:
                self._path_cache[cache_key] = path
                return path
            for dst, fn in self._edges_for(current):
                if dst not in visited:
                    visited.add(dst)
                    queue.append([*path, (current, dst, fn)])

        raise ValueError(
            f"No migration path from {from_ver!r} to {to_ver!r}. "
            f"Reachable versions exhausted."
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
        if target is None:  # pragma: no cover — defensive; from_legacy always delegates
            raise ValueError("Schema has no target version; cannot migrate.")

        if schema_version == target:
            # Already at target — return raw bytes for caller to decode.
            return data.read()  # type: ignore[return-value]

        path = self._find_path(schema_version, target)
        if not path:  # pragma: no cover — from_ver==to_ver caught above
            return data.read()  # type: ignore[return-value]

        result: Any = data
        for _src, _dst, fn in path:
            if not isinstance(result, (io.IOBase, io.BufferedIOBase)):
                # fn returned a decoded struct/basemodel — re-encode for
                # the next step so it receives IO[bytes].
                result = io.BytesIO(self._encode_intermediate(result))
            result = fn(result)

        return result  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Intermediate encoding
    # ------------------------------------------------------------------

    def _encode_intermediate(self, obj: Any) -> bytes:
        """Encode a decoded intermediate object back to bytes.

        Handles ``bytes``, ``msgspec.Struct`` (via the Schema's encoder),
        and Pydantic ``BaseModel`` (v1/v2 via ``pydantic_to_dict``).
        """
        if isinstance(obj, bytes):
            return obj
        try:
            return self._encoder.encode(obj)
        except TypeError:
            # Pydantic BaseModel — convert to dict first, then encode.
            return self._encoder.encode(pydantic_to_dict(obj))

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

        Note: the returned Schema has ``resource_type = None`` because
        ``IMigration`` does not carry type information.
        """
        from autocrud.types import IMigration

        if not isinstance(migration, IMigration):
            raise TypeError(
                f"Expected IMigration instance, got {type(migration).__name__}"
            )

        schema: Schema[T] = cls.__new__(cls)
        schema._resource_type = None  # type: ignore[assignment]
        schema._version = migration.schema_version  # type: ignore[assignment]
        schema._raw_validator = None
        schema._validator = None
        schema._chains = []
        schema._current_chain = []
        schema._explicit_to = {}
        schema._graph = None
        schema._regex_edges = []
        schema._path_cache = {}
        schema._legacy_migration = migration
        schema._encoder = msgspec.json.Encoder()
        return schema

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def resource_type(self) -> type[T] | None:
        """The resource type this Schema is bound to.

        Returns ``None`` for schemas created via ``from_legacy()``.
        """
        return self._resource_type

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
        rt = getattr(self._resource_type, "__name__", repr(self._resource_type))
        parts = [f"Schema({rt}, {self._version!r}"]
        if self._validator is not None:
            parts[0] += ", validator=..."
        parts[0] += ")"
        all_chains: list[
            list[tuple[str | re.Pattern[str], Callable[[IO[bytes]], Any]]]
        ] = list(self._chains)
        if self._current_chain:
            all_chains.append(self._current_chain)
        for chain_idx, chain in enumerate(all_chains):
            for step_idx, (from_ver, _fn) in enumerate(chain):
                if chain_idx > 0 and step_idx == 0:
                    method = ".plus"
                else:
                    method = ".step"
                if isinstance(from_ver, re.Pattern):
                    parts.append(f"{method}(re.compile({from_ver.pattern!r}), ...)")
                else:
                    parts.append(f"{method}({from_ver!r}, ...)")
        return "".join(parts)
