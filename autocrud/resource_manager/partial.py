from typing import Any, Iterable, TypeVar, get_args, get_origin, Union
import msgspec
from msgspec import Struct, defstruct, UnsetType, UNSET
from jsonpointer import JsonPointer
import types

T = TypeVar("T")


def _normalize_paths(partial: Iterable[str | JsonPointer]) -> list[list[str]]:
    paths = []
    for p in partial:
        if isinstance(p, JsonPointer):
            parts = p.parts
        else:
            parts = p.split("/")

        parts = [x for x in parts if x]
        paths.append(parts)
    return paths


def _merge_paths(paths: list[list[str]]) -> dict[str, list[list[str]]]:
    grouped = {}
    for p in paths:
        if not p:
            continue
        head = p[0]
        tail = p[1:]
        if head not in grouped:
            grouped[head] = []
        grouped[head].append(tail)
    return grouped


def _get_struct_fields(struct_type: type[Struct]) -> dict[str, Any]:
    return {f.name: f for f in msgspec.structs.fields(struct_type)}


def create_partial_type(base_type: Any, partial: Iterable[str | JsonPointer]) -> Any:
    paths = _normalize_paths(partial)
    return _build_type(base_type, paths, prefix="Partial")


def _build_type(current_type: Any, paths: list[list[str]], prefix: str) -> Any:
    if any(len(p) == 0 for p in paths):
        return current_type

    origin = get_origin(current_type)
    args = get_args(current_type)

    if origin is Union or origin is types.UnionType:
        new_args = []
        for arg in args:
            if arg is type(None):
                new_args.append(arg)
            else:
                new_args.append(_build_type(arg, paths, prefix))

        if len(new_args) == 2 and type(None) in new_args:
            other = new_args[0] if new_args[1] is type(None) else new_args[1]
            return other | None
        return Union[tuple(new_args)]

    if origin is list or origin is list:
        sub_paths = []
        for p in paths:
            if len(p) > 0:
                sub_paths.append(p[1:])

        element_type = args[0]
        new_element_type = _build_type(element_type, sub_paths, prefix + "Item")
        return list[new_element_type]

    if isinstance(current_type, type) and issubclass(current_type, Struct):
        fields = _get_struct_fields(current_type)
        grouped_paths = _merge_paths(paths)

        new_fields = []
        for field_name, sub_paths in grouped_paths.items():
            if field_name in fields:
                field_def = fields[field_name]
                field_type = field_def.type

                new_field_type = _build_type(
                    field_type, sub_paths, f"{prefix}_{field_name}"
                )

                # Add UnsetType to allow pruning
                if (
                    get_origin(new_field_type) is Union
                    or get_origin(new_field_type) is types.UnionType
                ):
                    args = get_args(new_field_type)
                    if UnsetType not in args:
                        new_field_type = Union[tuple(list(args) + [UnsetType])]
                else:
                    if new_field_type is not UnsetType:
                        new_field_type = new_field_type | UnsetType

                new_fields.append(
                    (
                        field_name,
                        new_field_type,
                        msgspec.field(
                            default=field_def.default,
                            default_factory=field_def.default_factory,
                            name=field_def.name,
                        ),
                    )
                )

        type_name = f"{prefix}_{current_type.__name__}"

        # Keep tag info
        kwargs = {}
        try:
            info = msgspec.inspect.type_info(current_type)
            kwargs["tag"] = info.tag
            kwargs["tag_field"] = info.tag_field
            kwargs["array_like"] = info.array_like
            kwargs["forbid_unknown_fields"] = info.forbid_unknown_fields
        except Exception:
            pass

        return defstruct(type_name, new_fields, kw_only=True, **kwargs)

    return current_type


def prune_object(obj: Any, partial: Iterable[str | JsonPointer]) -> Any:
    paths = _normalize_paths(partial)
    if not _needs_pruning(paths):
        return obj
    return _prune(obj, paths)


def _needs_pruning(paths: list[list[str]]) -> bool:
    for path in paths:
        for part in path:
            # Check if part is a specific index (digit)
            if part.isdigit() or (part.startswith("-") and part[1:].isdigit()):
                return True

            # Check if part is a slice
            if ":" in part:
                s = _parse_slice(part)
                if s:
                    # If it's not a full slice, we need pruning
                    if not (
                        s.start is None
                        and s.stop is None
                        and (s.step is None or s.step == 1)
                    ):
                        return True
    return False


def _parse_slice(s: str) -> slice | None:
    if ":" not in s:
        return None
    parts = s.split(":")
    if len(parts) > 3:
        return None

    try:
        start = int(parts[0]) if parts[0] else None
        stop = int(parts[1]) if len(parts) > 1 and parts[1] else None
        step = int(parts[2]) if len(parts) > 2 and parts[2] else None
        return slice(start, stop, step)
    except ValueError:
        return None


def _prune(obj: Any, paths: list[list[str]]) -> Any:
    if any(len(p) == 0 for p in paths):
        return obj

    if isinstance(obj, list):
        wildcard_subpaths = [p[1:] for p in paths if p and p[0] == "-"]
        has_wildcard = len(wildcard_subpaths) > 0

        other_paths = [p for p in paths if p and p[0] != "-"]

        if not other_paths:
            if has_wildcard:
                return obj
            return []

        obj_len = len(obj)
        slices = []
        specific_indices = {}

        for p in other_paths:
            head = p[0]
            s = _parse_slice(head)
            if s:
                slices.append((s, p[1:]))
            else:
                try:
                    idx = int(head)
                    if idx < 0:
                        idx += obj_len
                    if 0 <= idx < obj_len:
                        if idx not in specific_indices:
                            specific_indices[idx] = []
                        specific_indices[idx].append(p[1:])
                except ValueError:
                    pass

        # Optimization: If all paths are universal (wildcard or full slice) and no specific indices,
        # then the object structure already matches the request (handled by create_partial_type),
        # so we can return it as is.
        if not specific_indices:
            all_slices_full = True
            for s, _ in slices:
                if not (
                    s.start is None
                    and s.stop is None
                    and (s.step is None or s.step == 1)
                ):
                    all_slices_full = False
                    break

            if all_slices_full:
                return obj

        if has_wildcard:
            indices_to_process = range(obj_len)
        else:
            indices = set(specific_indices.keys())
            for s, _ in slices:
                indices.update(range(*s.indices(obj_len)))
            indices_to_process = sorted(indices)

        new_list = []
        for i in indices_to_process:
            item = obj[i]

            current_subpaths = list(wildcard_subpaths)

            if i in specific_indices:
                current_subpaths.extend(specific_indices[i])

            for s, sub in slices:
                start, stop, step = s.indices(obj_len)
                in_slice = False
                if step > 0:
                    if start <= i < stop and (i - start) % step == 0:
                        in_slice = True
                else:
                    if start >= i > stop and (start - i) % (-step) == 0:
                        in_slice = True

                if in_slice:
                    current_subpaths.append(sub)

            new_list.append(_prune(item, current_subpaths))

        return new_list

    if isinstance(obj, Struct):
        grouped = _merge_paths(paths)
        changes = {}

        fields = msgspec.structs.fields(type(obj))
        for f in fields:
            field_name = f.name
            val = getattr(obj, field_name)

            if field_name in grouped:
                if val is not UNSET:
                    sub_paths = grouped[field_name]
                    pruned_val = _prune(val, sub_paths)
                    if pruned_val is not val:
                        changes[field_name] = pruned_val
            else:
                if val is not UNSET:
                    changes[field_name] = UNSET

        if changes:
            return msgspec.structs.replace(obj, **changes)
        return obj

    return obj
