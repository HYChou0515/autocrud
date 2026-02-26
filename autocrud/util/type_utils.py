"""Unified type introspection utilities for the AutoCRUD framework.

This module provides **purpose-driven** helpers for type inspection so that
callers never need to import low-level primitives like ``get_origin``,
``get_args``, or ``get_type_hints`` from ``typing`` directly.

Covered domains:

- **Struct types**: concrete classes *and* generic aliases (e.g. ``Job[Payload]``)
- **Union / Optional types**: including PEP 604 ``A | B`` syntax
- **Annotated types**: ``Annotated[T, meta1, meta2, ...]``
- **Collection types**: ``list[X]``, ``dict[K, V]``, ``set[X]``, ``tuple[X, ...]``
- **Literal types**: ``Literal["a", "b"]``
- **TypeVar resolution**: building concrete TypeVar maps from class hierarchies
- **Struct discovery**: recursively collecting nested Struct types
- **Generic subclass checks**: e.g. "is this model a Job?" including parameterised forms

Centralising these checks prevents the class of bugs where a fix is applied in
one file but missed in another.
"""

from __future__ import annotations

import types as _builtin_types
from typing import (
    Annotated,
    Any,
    Literal,
    TypeVar,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

import msgspec
from msgspec import Struct

# ── Type hints (Annotated-aware) ────────────────────────────────────────────


def get_hints(cls: Any) -> dict[str, Any]:
    """Return the resolved type hints for *cls*, preserving ``Annotated`` metadata.

    Shorthand for ``get_type_hints(cls, include_extras=True)``.
    """
    return get_type_hints(cls, include_extras=True)


# ── Struct detection ─────────────────────────────────────────────────────────


def is_struct_type(type_hint: Any) -> bool:
    """Check if *type_hint* is a ``msgspec.Struct`` type.

    Returns ``True`` for:

    * **Concrete classes** — ``class Foo(Struct): ...``
    * **Generic aliases** — ``Foo[Bar]`` where ``Foo`` is a ``Struct`` subclass
    * **Subclasses of generics** — ``class MyFoo(Foo[Bar]): ...``

    .. note::

       This includes ``Binary`` and any other Struct subclass.  If a caller
       needs to exclude a specific Struct (e.g. ``Binary``), it should perform
       that check separately *before* calling this helper.
    """
    if isinstance(type_hint, type) and issubclass(type_hint, Struct):
        return True
    origin = get_origin(type_hint)
    return (
        origin is not None and isinstance(origin, type) and issubclass(origin, Struct)
    )


def resolve_struct_origin(type_hint: Any) -> type[Struct] | None:
    """Return the concrete ``Struct`` class underlying *type_hint*.

    * For a concrete class → returns the class itself.
    * For a generic alias (``Job[Payload]``) → returns the origin (``Job``).
    * For anything else → returns ``None``.
    """
    if isinstance(type_hint, type) and issubclass(type_hint, Struct):
        return type_hint
    origin = get_origin(type_hint)
    if origin is not None and isinstance(origin, type) and issubclass(origin, Struct):
        return origin
    return None


def get_struct_fields(
    type_hint: Any,
) -> tuple[msgspec.structs.FieldInfo, ...]:
    """Return the fields of a ``Struct`` type or generic alias.

    ``msgspec.structs.fields()`` natively supports both concrete types **and**
    generic aliases (resolving TypeVars automatically), so this is a thin
    wrapper that makes the intent explicit and keeps the import in one place.
    """
    return msgspec.structs.fields(type_hint)


# ── Union / Optional ────────────────────────────────────────────────────────


def is_union_type(type_hint: Any) -> bool:
    """Check if *type_hint* is a ``Union`` type.

    Handles both ``typing.Union[A, B]`` and PEP 604 ``A | B`` syntax
    (``types.UnionType``).
    """
    origin = get_origin(type_hint)
    return origin is Union or origin is _builtin_types.UnionType


def is_optional_type(type_hint: Any) -> bool:
    """Check if *type_hint* is ``Optional[X]`` (i.e. ``Union[X, None]``)."""
    if not is_union_type(type_hint):
        return False
    return type(None) in get_args(type_hint)


def get_non_none_args(type_hint: Any) -> tuple[Any, ...]:
    """Return the non-``NoneType`` members of a Union.

    Returns an empty tuple if *type_hint* is not a Union.
    """
    if not is_union_type(type_hint):
        return ()
    return tuple(a for a in get_args(type_hint) if a is not type(None))


def get_union_args(type_hint: Any) -> tuple[Any, ...]:
    """Return **all** members of a ``Union`` (including ``NoneType``).

    Returns an empty tuple if *type_hint* is not a Union.
    """
    if not is_union_type(type_hint):
        return ()
    return get_args(type_hint)


# ── Annotated ───────────────────────────────────────────────────────────────


def is_annotated_type(type_hint: Any) -> bool:
    """Check if *type_hint* is ``Annotated[T, ...]``."""
    return get_origin(type_hint) is Annotated


def unwrap_annotated(type_hint: Any) -> tuple[Any, tuple[Any, ...]]:
    """Unwrap ``Annotated[T, meta1, meta2, ...]``.

    Returns ``(T, (meta1, meta2, ...))`` if *type_hint* is ``Annotated``,
    or ``(type_hint, ())`` otherwise.
    """
    if not is_annotated_type(type_hint):
        return type_hint, ()
    args = get_args(type_hint)
    return args[0], tuple(args[1:])


# ── Collection types ────────────────────────────────────────────────────────


def is_list_type(type_hint: Any) -> bool:
    """Check if *type_hint* is a parameterised ``list`` type.

    Handles both modern ``list[X]`` and legacy ``typing.List[X]``.
    Both have ``get_origin(...) is list`` in Python 3.9+.
    """
    return get_origin(type_hint) is list


def is_dict_type(type_hint: Any) -> bool:
    """Check if *type_hint* is a parameterised ``dict`` type.

    Handles both modern ``dict[K, V]`` and legacy ``typing.Dict[K, V]``.
    """
    return get_origin(type_hint) is dict


def is_set_type(type_hint: Any) -> bool:
    """Check if *type_hint* is a parameterised ``set`` type."""
    return get_origin(type_hint) is set


def is_tuple_type(type_hint: Any) -> bool:
    """Check if *type_hint* is a parameterised ``tuple`` type."""
    return get_origin(type_hint) is tuple


def get_list_item_type(type_hint: Any) -> Any | None:
    """Return the element type of ``list[X]``, or ``None`` if not a list type."""
    if not is_list_type(type_hint):
        return None
    args = get_args(type_hint)
    return args[0] if args else None


def get_dict_value_type(type_hint: Any) -> Any | None:
    """Return the value type of ``dict[K, V]``, or ``None`` if not a dict type."""
    if not is_dict_type(type_hint):
        return None
    args = get_args(type_hint)
    return args[1] if args and len(args) == 2 else None


def get_dict_key_type(type_hint: Any) -> Any | None:
    """Return the key type of ``dict[K, V]``, or ``None`` if not a dict type."""
    if not is_dict_type(type_hint):
        return None
    args = get_args(type_hint)
    return args[0] if args else None


def get_set_item_type(type_hint: Any) -> Any | None:
    """Return the element type of ``set[X]``, or ``None`` if not a set type."""
    if not is_set_type(type_hint):
        return None
    args = get_args(type_hint)
    return args[0] if args else None


def get_tuple_item_types(type_hint: Any) -> tuple[Any, ...] | None:
    """Return all element types of ``tuple[X, Y, ...]``.

    Returns ``None`` if *type_hint* is not a tuple type.
    """
    if not is_tuple_type(type_hint):
        return None
    return get_args(type_hint)


# ── Literal types ───────────────────────────────────────────────────────────


def is_literal_type(type_hint: Any) -> bool:
    """Check if *type_hint* is a ``Literal[...]`` type."""
    return get_origin(type_hint) is Literal


def get_literal_values(type_hint: Any) -> tuple[Any, ...]:
    """Return the values of a ``Literal[v1, v2, ...]`` type.

    Returns an empty tuple if *type_hint* is not a ``Literal``.

    Example::

        get_literal_values(Literal["cat", "dog"])  # → ("cat", "dog")
    """
    if not is_literal_type(type_hint):
        return ()
    return get_args(type_hint)


# ── Generic type introspection ──────────────────────────────────────────────


def get_inner_types(type_hint: Any) -> tuple[Any, ...]:
    """Return the child type arguments of any parameterised generic type.

    This is the correct tool for **recursive type-tree traversal** — when you
    need to walk into all child types of a generic type regardless of its
    container kind (Union, list, dict, Annotated, etc.).

    Returns an empty tuple for non-generic types.

    Examples::

        get_inner_types(list[int])  # → (int,)
        get_inner_types(dict[str, int])  # → (str, int)
        get_inner_types(Union[A, B])  # → (A, B)
        get_inner_types(int)  # → ()
    """
    return get_args(type_hint)


def get_generic_origin(type_hint: Any) -> Any | None:
    """Return the generic origin of a parameterised type.

    Falls back to the ``__origin__`` attribute for compatibility with
    types that define it outside the standard ``typing`` machinery
    (e.g. Pydantic v1 annotations).

    Returns ``None`` for non-generic types.
    """
    return get_origin(type_hint) or getattr(type_hint, "__origin__", None)


def get_generic_args(type_hint: Any) -> tuple[Any, ...]:
    """Return the type arguments of a parameterised generic type.

    Falls back to the ``__args__`` attribute for compatibility with
    types that define it outside the standard ``typing`` machinery.

    Returns an empty tuple for non-generic types.
    """
    return get_args(type_hint) or getattr(type_hint, "__args__", ())


# ── TypeVar resolution ──────────────────────────────────────────────────────


def build_typevar_map(cls: type) -> dict[TypeVar, type]:
    """Build a ``TypeVar → concrete type`` mapping from *cls*'s ``__orig_bases__``.

    Walks the class hierarchy recursively so that deeply-nested generic chains
    (e.g. ``MyJob(Job[T])`` where ``Job(Struct, Generic[T])``) are resolved.

    Example::

        class Job(Struct, Generic[T]):
            payload: T


        class MyJob(Job[MyPayload]):
            pass


        build_typevar_map(MyJob)  # → {T: MyPayload}
    """
    mapping: dict[TypeVar, type] = {}
    for base in getattr(cls, "__orig_bases__", ()):
        origin = get_origin(base)
        args = get_args(base)
        if origin is not None and args:
            params = getattr(origin, "__parameters__", ())
            for param, arg in zip(params, args):
                if isinstance(param, TypeVar):
                    mapping[param] = arg
            # Recurse into the origin class for deeper generic chains
            mapping.update(build_typevar_map(origin))
    return mapping


# ── Struct discovery ────────────────────────────────────────────────────────


def collect_nested_struct_types(
    struct_type: type,
    visited: set[type] | None = None,
) -> list[type]:
    """Recursively collect all ``Struct`` types referenced by *struct_type*'s fields.

    Resolves TypeVar parameters (e.g. ``Job[T]`` with ``T = MyPayload``) so
    that concrete nested payloads are discovered.

    Returns a list of Struct types (excluding *struct_type* itself) in
    discovery order.  *visited* tracks already-seen types to avoid cycles.
    """
    if visited is None:
        visited = set()
    if struct_type in visited:
        return []
    visited.add(struct_type)

    result: list[type] = []
    try:
        hints = get_hints(struct_type)
    except Exception:
        return result

    tv_map = build_typevar_map(struct_type)

    for hint in hints.values():
        resolved = tv_map.get(hint, hint) if isinstance(hint, TypeVar) else hint
        _walk_hint_for_structs(resolved, visited, result, tv_map)
    return result


def _walk_hint_for_structs(
    hint: Any,
    visited: set[type],
    out: list[type],
    tv_map: dict[TypeVar, type],
) -> None:
    """Internal: walk a single type hint and collect Struct types into *out*."""
    # Resolve lingering TypeVars
    if isinstance(hint, TypeVar):
        resolved = tv_map.get(hint)
        if resolved is not None:
            hint = resolved
        else:
            return

    # Annotated — unwrap and recurse into the inner type
    if is_annotated_type(hint):
        inner, _meta = unwrap_annotated(hint)
        _walk_hint_for_structs(inner, visited, out, tv_map)
        return

    origin = get_origin(hint)
    if origin is not None:
        # Generic Struct alias (e.g. Job[Payload]) — register the origin class
        if is_struct_type(hint):
            concrete = origin
            if concrete not in visited:
                out.append(concrete)
                out.extend(collect_nested_struct_types(concrete, visited))
        # Walk all type arguments for nested Structs
        for arg in get_args(hint):
            _walk_hint_for_structs(arg, visited, out, tv_map)
        return

    # Plain type — check if it's a Struct subclass
    if isinstance(hint, type) and issubclass(hint, Struct):
        if hint not in visited:
            out.append(hint)
            out.extend(collect_nested_struct_types(hint, visited))


# ── Generic subclass check ──────────────────────────────────────────────────


def is_generic_subclass(model: Any, target_cls: type) -> bool:
    """Check if *model* is *target_cls*, a parameterisation of it, or a subclass.

    Handles all three forms:

    * ``is_generic_subclass(Job, Job)`` → ``True``
    * ``is_generic_subclass(Job[Payload], Job)`` → ``True``
    * ``is_generic_subclass(MyJob, Job)`` → ``True`` (where ``MyJob(Job[X])``)

    Also walks ``__mro__`` to detect deep inheritance chains.
    """
    try:
        # Direct identity or generic alias whose origin matches
        if model is target_cls:
            return True
        origin = get_origin(model)
        if origin is target_cls:
            return True

        # Walk MRO for concrete subclasses
        if not hasattr(model, "__mro__"):
            return False
        for base in model.__mro__:
            if base is target_cls:
                return True
            base_origin = get_origin(base)
            if base_origin is target_cls:
                return True

        return False
    except (AttributeError, TypeError):
        return False


# ── Field type resolution ───────────────────────────────────────────────────


def get_field_raw_type(
    struct_type: type, field_name: str, *, default: Any = None
) -> Any:
    """Return the raw (non-``Annotated``) type of *field_name* on *struct_type*.

    If the hint is ``Annotated[T, ...]``, returns ``T``.
    If the hint is a plain type, returns it as-is.
    Returns *default* when resolution fails or the field does not exist.

    Example::

        class User(Struct):
            name: Annotated[str, Unique()]
            age: int


        get_field_raw_type(User, "name")  # → str
        get_field_raw_type(User, "age")  # → int
        get_field_raw_type(User, "nope")  # → None
    """
    try:
        hints = get_hints(struct_type)
        hint = hints.get(field_name)
        if hint is not None and is_annotated_type(hint):
            inner, _metadata = unwrap_annotated(hint)
            return inner
        if hint is not None:
            return hint
    except Exception:
        pass
    return default


# ── Nullable detection ──────────────────────────────────────────────────────


def is_nullable_type(type_hint: Any) -> bool:
    """Check if *type_hint* is nullable — ``Optional[X]``, ``X | None``, or ``NoneType`` itself.

    Unlike :func:`is_optional_type` which only matches Union types containing
    ``None``, this also returns ``True`` for bare ``NoneType``.
    """
    return is_optional_type(type_hint) or type_hint is type(None)


# ── Annotation scanning ────────────────────────────────────────────────────


def find_annotated_fields(struct_type: type, marker_cls: type) -> list[str]:
    """Return field names whose ``Annotated`` metadata contains an instance of *marker_cls*.

    Scans all type hints of *struct_type*, unwraps ``Annotated[T, ...]``,
    and checks each metadata item with ``isinstance(meta, marker_cls)``.

    Returns field names in definition order.  Returns an empty list if
    type hints cannot be resolved or no matching annotations are found.

    Example::

        class DisplayName:
            pass


        class User(Struct):
            name: Annotated[str, DisplayName()]
            age: int


        find_annotated_fields(User, DisplayName)  # → ["name"]
    """
    result: list[str] = []
    try:
        hints = get_hints(struct_type)
    except Exception:
        return result
    for field_name, hint in hints.items():
        if is_annotated_type(hint):
            _inner, metadata = unwrap_annotated(hint)
            for meta in metadata:
                if isinstance(meta, marker_cls):
                    result.append(field_name)
                    break  # One match per field is enough
    return result


# ── Type name extraction ────────────────────────────────────────────────────


def get_type_name(type_hint: Any) -> str | None:
    """Extract the class name from any type hint.

    This is the fundamental name-extraction primitive.  It handles:

    * Concrete types (→ ``__name__``)
    * Generic aliases like ``Job[Payload]`` (→ origin's ``__name__``)
    * Union types like ``Cat | Dog`` (→ each member's name joined with ``"Or"``)
    * Everything else → ``None``

    Examples::

        get_type_name(int)  # → "int"
        get_type_name(Job[Payload])  # → "Job"
        get_type_name(Cat | Dog)  # → "CatOrDog"
        get_type_name(Cat | Dog | None)  # → "CatOrDog" (NoneType excluded)
        get_type_name(list[int])  # → "list" (builtins have __name__)
    """
    # Concrete type with __name__
    name = getattr(type_hint, "__name__", None)
    if name is not None:
        return name

    # Generic Struct alias (e.g. Job[Payload]) → origin class name
    origin = resolve_struct_origin(type_hint)
    if origin is not None:
        return origin.__name__

    # Union type (Cat | Dog) → concat member names, skip NoneType
    if is_union_type(type_hint):
        parts: list[str] = []
        for arg in get_union_args(type_hint):
            if arg is type(None):
                continue
            arg_name = getattr(arg, "__name__", None)
            if arg_name is None:
                return None  # Can't resolve a member → give up
            parts.append(arg_name)
        if parts:
            return "Or".join(parts)

    return None


# ── Type display name ───────────────────────────────────────────────────────


def get_type_display_name(type_hint: Any) -> str:
    """Return a human-readable name for *type_hint*.

    * Concrete types → ``type_hint.__name__``
    * Union types (``Cat | Dog``) → ``"CatUnion"``
    * Fallback → string representation with spaces/pipes cleaned

    Examples::

        get_type_display_name(int)  # → "int"
        get_type_display_name(Cat | Dog)  # → "CatUnion"
        get_type_display_name(list[int])  # → "list[int]" (fallback)
    """
    if hasattr(type_hint, "__name__"):
        return type_hint.__name__

    # Union types: use first member + "Union" suffix
    if is_union_type(type_hint):
        args = get_union_args(type_hint)
        if args:
            first_type = args[0]
            if hasattr(first_type, "__name__"):
                return f"{first_type.__name__}Union"
        return "UnionType"

    # Fallback
    return str(type_hint).replace(" ", "").replace("|", "Or")


# ── Container unwrapping ───────────────────────────────────────────────────


def unwrap_container_type(type_hint: Any) -> Any:
    """Recursively unwrap ``list`` and ``Optional`` wrappers to get the inner concrete type.

    Peels through any nesting of ``list[...]`` and ``Optional[...]`` /
    ``X | None`` to reach the underlying element type.

    Examples::

        unwrap_container_type(list[int])  # → int
        unwrap_container_type(list[list[str]])  # → str
        unwrap_container_type(Optional[list[User]])  # → User
        unwrap_container_type(str)  # → str
    """
    if is_list_type(type_hint):
        return unwrap_container_type(get_list_item_type(type_hint))
    if is_optional_type(type_hint):
        non_none = get_non_none_args(type_hint)
        if len(non_none) == 1:
            return unwrap_container_type(non_none[0])
    return type_hint


def get_list_nesting_depth(type_hint: Any) -> int:
    """Count the nesting depth of ``list`` wrappers.

    Examples::

        get_list_nesting_depth(int)  # → 0
        get_list_nesting_depth(list[int])  # → 1
        get_list_nesting_depth(list[list[str]])  # → 2
    """
    depth = 0
    while is_list_type(type_hint):
        depth += 1
        type_hint = get_list_item_type(type_hint)
    return depth
