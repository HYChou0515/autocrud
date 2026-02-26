"""Tests for autocrud.util.type_utils — unified type introspection helpers."""

from __future__ import annotations

from typing import Annotated, Generic, Literal, Optional, TypeVar, Union

from msgspec import Struct

from autocrud.types import Binary, DisplayName, Job, Unique
from autocrud.util.type_utils import (
    build_typevar_map,
    collect_nested_struct_types,
    find_annotated_fields,
    get_dict_key_type,
    get_dict_value_type,
    get_field_raw_type,
    get_generic_args,
    get_generic_origin,
    get_hints,
    get_inner_types,
    get_list_item_type,
    get_list_nesting_depth,
    get_literal_values,
    get_non_none_args,
    get_set_item_type,
    get_struct_fields,
    get_tuple_item_types,
    get_type_display_name,
    get_type_name,
    get_union_args,
    is_annotated_type,
    is_dict_type,
    is_generic_subclass,
    is_list_type,
    is_literal_type,
    is_nullable_type,
    is_optional_type,
    is_set_type,
    is_struct_type,
    is_tuple_type,
    is_union_type,
    resolve_struct_origin,
    unwrap_annotated,
    unwrap_container_type,
)

T = TypeVar("T")
U = TypeVar("U")


# ── Test Structs ────────────────────────────────────────────────────────────


class SimpleStruct(Struct):
    x: int
    y: str


class Inner(Struct):
    value: Binary


class Outer(Struct, Generic[T]):
    payload: T
    name: str = "default"


class ConcreteOuter(Outer[Inner]):
    pass


class MyPayload(Struct):
    data: Inner
    age: int


class MyJob(Job[MyPayload]):
    pass


# ── is_struct_type ──────────────────────────────────────────────────────────


class TestIsStructType:
    def test_concrete_struct(self):
        assert is_struct_type(SimpleStruct) is True

    def test_binary_is_struct(self):
        # Binary IS a Struct — callers that need to exclude it check separately
        assert is_struct_type(Binary) is True

    def test_generic_alias(self):
        assert is_struct_type(Outer[Inner]) is True

    def test_job_generic_alias(self):
        assert is_struct_type(Job[MyPayload]) is True

    def test_concrete_subclass_of_generic(self):
        assert is_struct_type(ConcreteOuter) is True
        assert is_struct_type(MyJob) is True

    def test_not_struct(self):
        assert is_struct_type(int) is False
        assert is_struct_type(str) is False
        assert is_struct_type(list[int]) is False
        assert is_struct_type(dict[str, int]) is False

    def test_none_and_special_values(self):
        assert is_struct_type(None) is False
        assert is_struct_type(type(None)) is False

    def test_union_is_not_struct(self):
        assert is_struct_type(int | str) is False
        assert is_struct_type(Optional[SimpleStruct]) is False


# ── resolve_struct_origin ───────────────────────────────────────────────────


class TestResolveStructOrigin:
    def test_concrete_struct(self):
        assert resolve_struct_origin(SimpleStruct) is SimpleStruct

    def test_generic_alias_returns_origin(self):
        assert resolve_struct_origin(Outer[Inner]) is Outer

    def test_job_alias_returns_job(self):
        assert resolve_struct_origin(Job[MyPayload]) is Job

    def test_concrete_subclass(self):
        assert resolve_struct_origin(MyJob) is MyJob

    def test_non_struct_returns_none(self):
        assert resolve_struct_origin(int) is None
        assert resolve_struct_origin(list[int]) is None
        assert resolve_struct_origin(None) is None


# ── get_struct_fields ───────────────────────────────────────────────────────


class TestGetStructFields:
    def test_concrete_struct(self):
        fields = get_struct_fields(SimpleStruct)
        names = [f.name for f in fields]
        assert names == ["x", "y"]

    def test_generic_alias_resolves_typevar(self):
        fields = get_struct_fields(Outer[Inner])
        field_map = {f.name: f.type for f in fields}
        assert field_map["payload"] is Inner
        assert field_map["name"] is str

    def test_job_alias_resolves_payload(self):
        fields = get_struct_fields(Job[MyPayload])
        field_map = {f.name: f.type for f in fields}
        assert field_map["payload"] is MyPayload

    def test_concrete_subclass_resolves_typevar(self):
        fields = get_struct_fields(MyJob)
        field_map = {f.name: f.type for f in fields}
        assert field_map["payload"] is MyPayload


# ── is_union_type ───────────────────────────────────────────────────────────


class TestIsUnionType:
    def test_typing_union(self):
        assert is_union_type(Union[int, str]) is True

    def test_pep604_union(self):
        assert is_union_type(int | str) is True

    def test_optional_is_union(self):
        assert is_union_type(Optional[int]) is True

    def test_not_union(self):
        assert is_union_type(int) is False
        assert is_union_type(list[int]) is False
        assert is_union_type(SimpleStruct) is False


# ── is_optional_type ────────────────────────────────────────────────────────


class TestIsOptionalType:
    def test_optional(self):
        assert is_optional_type(Optional[int]) is True

    def test_union_with_none(self):
        assert is_optional_type(int | None) is True
        assert is_optional_type(Union[str, None]) is True

    def test_union_without_none(self):
        assert is_optional_type(int | str) is False

    def test_not_union(self):
        assert is_optional_type(int) is False


# ── get_non_none_args ───────────────────────────────────────────────────────


class TestGetNonNoneArgs:
    def test_optional(self):
        assert get_non_none_args(Optional[int]) == (int,)

    def test_union_with_none(self):
        result = get_non_none_args(Union[int, str, None])
        assert set(result) == {int, str}

    def test_union_without_none(self):
        result = get_non_none_args(int | str)
        assert set(result) == {int, str}

    def test_not_union(self):
        assert get_non_none_args(int) == ()


# ── is_annotated_type ───────────────────────────────────────────────────────


class TestIsAnnotatedType:
    def test_annotated(self):
        assert is_annotated_type(Annotated[int, "meta"]) is True

    def test_not_annotated(self):
        assert is_annotated_type(int) is False
        assert is_annotated_type(Optional[int]) is False


# ── unwrap_annotated ────────────────────────────────────────────────────────


class TestUnwrapAnnotated:
    def test_annotated(self):
        inner, metadata = unwrap_annotated(Annotated[int, "meta1", "meta2"])
        assert inner is int
        assert metadata == ("meta1", "meta2")

    def test_not_annotated_passthrough(self):
        inner, metadata = unwrap_annotated(int)
        assert inner is int
        assert metadata == ()


# ── is_list_type / is_dict_type ─────────────────────────────────────────────


class TestCollectionTypes:
    def test_list_type(self):
        assert is_list_type(list[int]) is True
        assert is_list_type(list[SimpleStruct]) is True

    def test_not_list_type(self):
        assert is_list_type(list) is False
        assert is_list_type(int) is False
        assert is_list_type(dict[str, int]) is False

    def test_dict_type(self):
        assert is_dict_type(dict[str, int]) is True

    def test_not_dict_type(self):
        assert is_dict_type(dict) is False
        assert is_dict_type(int) is False
        assert is_dict_type(list[int]) is False


# ── is_set_type / is_tuple_type ─────────────────────────────────────────────


class TestSetTupleTypes:
    def test_set_type(self):
        assert is_set_type(set[int]) is True
        assert is_set_type(set[str]) is True

    def test_not_set_type(self):
        assert is_set_type(set) is False
        assert is_set_type(int) is False
        assert is_set_type(list[int]) is False

    def test_tuple_type(self):
        assert is_tuple_type(tuple[int, str]) is True
        assert is_tuple_type(tuple[int, ...]) is True

    def test_not_tuple_type(self):
        assert is_tuple_type(tuple) is False
        assert is_tuple_type(int) is False
        assert is_tuple_type(list[int]) is False


# ── get_list_item_type / get_dict_value_type ────────────────────────────────


class TestGetItemTypes:
    def test_list_item_type(self):
        assert get_list_item_type(list[int]) is int
        assert get_list_item_type(list[SimpleStruct]) is SimpleStruct

    def test_list_item_type_not_list(self):
        assert get_list_item_type(int) is None
        assert get_list_item_type(dict[str, int]) is None

    def test_dict_value_type(self):
        assert get_dict_value_type(dict[str, int]) is int
        assert get_dict_value_type(dict[str, SimpleStruct]) is SimpleStruct

    def test_dict_value_type_not_dict(self):
        assert get_dict_value_type(int) is None
        assert get_dict_value_type(list[int]) is None

    def test_dict_key_type(self):
        assert get_dict_key_type(dict[str, int]) is str
        assert get_dict_key_type(dict[int, SimpleStruct]) is int

    def test_dict_key_type_not_dict(self):
        assert get_dict_key_type(int) is None
        assert get_dict_key_type(list[int]) is None


# ── get_union_args ──────────────────────────────────────────────────────────


class TestGetUnionArgs:
    def test_typing_union(self):
        result = get_union_args(Union[int, str])
        assert set(result) == {int, str}

    def test_pep604_union(self):
        result = get_union_args(int | str)
        assert set(result) == {int, str}

    def test_optional_includes_none(self):
        result = get_union_args(Optional[int])
        assert int in result
        assert type(None) in result

    def test_not_union(self):
        assert get_union_args(int) == ()
        assert get_union_args(list[int]) == ()


# ── get_inner_types ─────────────────────────────────────────────────────────


class TestGetInnerTypes:
    """get_inner_types: walk child types of any parameterised generic."""

    def test_list(self):
        assert get_inner_types(list[int]) == (int,)

    def test_dict(self):
        assert get_inner_types(dict[str, int]) == (str, int)

    def test_union(self):
        result = get_inner_types(Union[int, str])
        assert set(result) == {int, str}

    def test_plain_type(self):
        assert get_inner_types(int) == ()

    def test_generic_struct(self):
        assert get_inner_types(Outer[Inner]) == (Inner,)


# ── get_generic_origin / get_generic_args ───────────────────────────────────


class TestGenericOriginArgs:
    """Purpose: decompose generic types for reconstruction (e.g. pydantic_converter)."""

    def test_generic_origin_list(self):
        assert get_generic_origin(list[int]) is list

    def test_generic_origin_struct(self):
        assert get_generic_origin(Outer[Inner]) is Outer

    def test_generic_origin_plain(self):
        assert get_generic_origin(int) is None

    def test_generic_args_list(self):
        assert get_generic_args(list[int]) == (int,)

    def test_generic_args_dict(self):
        assert get_generic_args(dict[str, int]) == (str, int)

    def test_generic_args_plain(self):
        assert get_generic_args(int) == ()


# ── Literal types ───────────────────────────────────────────────────────────


class TestLiteralTypes:
    def test_is_literal(self):
        assert is_literal_type(Literal["cat", "dog"]) is True

    def test_is_not_literal(self):
        assert is_literal_type(str) is False
        assert is_literal_type(list[int]) is False

    def test_get_literal_values(self):
        assert get_literal_values(Literal["cat", "dog"]) == ("cat", "dog")

    def test_get_literal_values_int(self):
        assert get_literal_values(Literal[1, 2, 3]) == (1, 2, 3)

    def test_get_literal_values_not_literal(self):
        assert get_literal_values(str) == ()


# ── build_typevar_map ───────────────────────────────────────────────────────


class TestBuildTypevarMap:
    def test_concrete_subclass(self):
        tv_map = build_typevar_map(MyJob)
        assert MyPayload in tv_map.values()

    def test_concrete_outer(self):
        tv_map = build_typevar_map(ConcreteOuter)
        assert Inner in tv_map.values()

    def test_plain_struct(self):
        assert build_typevar_map(SimpleStruct) == {}


# ── collect_nested_struct_types ─────────────────────────────────────────────


class TestCollectNestedStructTypes:
    def test_simple_struct(self):
        """SimpleStruct has no nested Struct fields."""
        assert collect_nested_struct_types(SimpleStruct) == []

    def test_nested_struct(self):
        """Outer[Inner] has Inner as a nested Struct."""

        class Container(Struct):
            child: Inner

        nested = collect_nested_struct_types(Container)
        assert Inner in nested

    def test_generic_struct_resolves_typevar(self):
        """MyJob(Job[MyPayload]) should discover MyPayload and Inner inside it."""
        nested = collect_nested_struct_types(MyJob)
        nested_set = set(nested)
        assert MyPayload in nested_set
        assert Inner in nested_set

    def test_no_cycles(self):
        """Repeated references don't cause infinite recursion."""

        class Wrapper(Struct):
            inner1: Inner
            inner2: Inner

        nested = collect_nested_struct_types(Wrapper)
        # Inner should appear only once despite two references
        assert Inner in nested


# ── is_generic_subclass ─────────────────────────────────────────────────────


class TestIsGenericSubclass:
    def test_direct_class(self):
        assert is_generic_subclass(Job, Job) is True

    def test_generic_alias(self):
        assert is_generic_subclass(Job[MyPayload], Job) is True

    def test_concrete_subclass(self):
        assert is_generic_subclass(MyJob, Job) is True

    def test_not_subclass(self):
        assert is_generic_subclass(SimpleStruct, Job) is False
        assert is_generic_subclass(int, Job) is False

    def test_non_type(self):
        assert is_generic_subclass(list[int], Job) is False


# ── get_set_item_type / get_tuple_item_types ────────────────────────────────


class TestSetTupleGetters:
    def test_set_item_type(self):
        assert get_set_item_type(set[int]) is int

    def test_set_item_type_not_set(self):
        assert get_set_item_type(int) is None

    def test_tuple_item_types(self):
        assert get_tuple_item_types(tuple[int, str]) == (int, str)

    def test_tuple_item_types_not_tuple(self):
        assert get_tuple_item_types(int) is None


# ── get_hints ───────────────────────────────────────────────────────────────


class TestGetHints:
    def test_simple_struct(self):
        hints = get_hints(SimpleStruct)
        assert "x" in hints
        assert hints["x"] is int

    def test_annotated_preserved(self):
        """get_hints returns Annotated forms (include_extras=True)."""

        class WithAnnotated(Struct):
            val: Annotated[int, "some_meta"]

        hints = get_hints(WithAnnotated)
        # The hint should still be Annotated, not unwrapped int
        from autocrud.util.type_utils import is_annotated_type

        assert is_annotated_type(hints["val"])


# ── is_nullable_type ────────────────────────────────────────────────────────


class TestIsNullableType:
    def test_optional_is_nullable(self):
        assert is_nullable_type(Optional[int]) is True

    def test_union_with_none_is_nullable(self):
        assert is_nullable_type(int | None) is True

    def test_bare_nonetype_is_nullable(self):
        assert is_nullable_type(type(None)) is True

    def test_plain_type_not_nullable(self):
        assert is_nullable_type(int) is False

    def test_union_without_none_not_nullable(self):
        assert is_nullable_type(int | str) is False

    def test_list_not_nullable(self):
        assert is_nullable_type(list[int]) is False


# ── find_annotated_fields ───────────────────────────────────────────────────


class _MarkerA:
    pass


class _MarkerB:
    pass


class TestFindAnnotatedFields:
    def test_single_marker(self):
        class Model(Struct):
            name: Annotated[str, _MarkerA()]
            age: int

        assert find_annotated_fields(Model, _MarkerA) == ["name"]

    def test_multiple_markers(self):
        class Model(Struct):
            x: Annotated[str, _MarkerA()]
            y: Annotated[int, _MarkerB()]
            z: Annotated[str, _MarkerA()]

        assert find_annotated_fields(Model, _MarkerA) == ["x", "z"]
        assert find_annotated_fields(Model, _MarkerB) == ["y"]

    def test_no_markers(self):
        class Model(Struct):
            x: int
            y: str

        assert find_annotated_fields(Model, _MarkerA) == []

    def test_mixed_annotated_and_plain(self):
        class Model(Struct):
            a: Annotated[str, _MarkerA()]
            b: int
            c: Annotated[str, "not_a_marker"]

        assert find_annotated_fields(Model, _MarkerA) == ["a"]

    def test_multiple_metadata_per_field(self):
        class Model(Struct):
            f: Annotated[str, "extra", _MarkerA(), _MarkerB()]

        assert find_annotated_fields(Model, _MarkerA) == ["f"]
        assert find_annotated_fields(Model, _MarkerB) == ["f"]

    def test_with_display_name_marker(self):
        """Integration test with real DisplayName marker from autocrud.types."""

        class Character(Struct):
            name: Annotated[str, DisplayName()]
            level: int = 1

        assert find_annotated_fields(Character, DisplayName) == ["name"]

    def test_with_unique_marker(self):
        """Integration test with real Unique marker from autocrud.types."""

        class User(Struct):
            username: Annotated[str, Unique()]
            email: Annotated[str, Unique()]
            age: int = 0

        assert find_annotated_fields(User, Unique) == ["username", "email"]

    def test_non_class_returns_empty(self):
        """Non-type input should return empty list, not raise."""
        assert find_annotated_fields(42, _MarkerA) == []  # type: ignore[arg-type]


# ── get_type_name ───────────────────────────────────────────────────────────


class TestGetTypeName:
    def test_concrete_type(self):
        assert get_type_name(int) == "int"

    def test_struct_type(self):
        assert get_type_name(SimpleStruct) == "SimpleStruct"

    def test_generic_struct_alias(self):
        assert get_type_name(Outer[Inner]) == "Outer"

    def test_union_type(self):
        class Cat(Struct):
            meow: str = ""

        class Dog(Struct):
            bark: str = ""

        assert get_type_name(Cat | Dog) == "CatOrDog"

    def test_union_with_none_excludes_nonetype(self):
        assert get_type_name(int | None) == "int"

    def test_list_has_name(self):
        # list[int] still has __name__ == "list" (builtin)
        assert get_type_name(list[int]) == "list"

    def test_job_generic(self):
        from autocrud.types import Job

        class Payload(Struct):
            x: int = 0

        assert get_type_name(Job[Payload]) == "Job"


# ── get_type_display_name ───────────────────────────────────────────────────


class TestGetTypeDisplayName:
    def test_concrete_type(self):
        assert get_type_display_name(int) == "int"

    def test_struct_type(self):
        assert get_type_display_name(SimpleStruct) == "SimpleStruct"

    def test_union_type(self):
        class Cat(Struct):
            meow: str = ""

        class Dog(Struct):
            bark: str = ""

        result = get_type_display_name(Cat | Dog)
        assert result == "CatUnion"

    def test_union_with_none(self):
        assert get_type_display_name(int | None) == "intUnion"

    def test_fallback(self):
        """Non-named, non-union types fall back to str representation."""
        result = get_type_display_name(list[int])
        assert isinstance(result, str)
        assert len(result) > 0


# ── unwrap_container_type ───────────────────────────────────────────────────


class TestUnwrapContainerType:
    def test_plain_type(self):
        assert unwrap_container_type(int) is int

    def test_single_list(self):
        assert unwrap_container_type(list[int]) is int

    def test_nested_list(self):
        assert unwrap_container_type(list[list[str]]) is str

    def test_optional(self):
        assert unwrap_container_type(Optional[int]) is int

    def test_optional_list(self):
        assert unwrap_container_type(Optional[list[str]]) is str

    def test_list_optional(self):
        assert unwrap_container_type(list[Optional[int]]) is int

    def test_struct_through_list(self):
        assert unwrap_container_type(list[SimpleStruct]) is SimpleStruct

    def test_deeply_nested(self):
        assert unwrap_container_type(list[list[list[float]]]) is float

    def test_multi_union_not_unwrapped(self):
        """Union[A, B] (non-Optional) should not be unwrapped."""
        hint = int | str
        assert unwrap_container_type(hint) == hint


# ── get_list_nesting_depth ──────────────────────────────────────────────────


class TestGetListNestingDepth:
    def test_non_list(self):
        assert get_list_nesting_depth(int) == 0

    def test_single_list(self):
        assert get_list_nesting_depth(list[int]) == 1

    def test_double_nested(self):
        assert get_list_nesting_depth(list[list[str]]) == 2

    def test_triple_nested(self):
        assert get_list_nesting_depth(list[list[list[float]]]) == 3

    def test_struct_type(self):
        assert get_list_nesting_depth(SimpleStruct) == 0

    def test_optional_not_counted(self):
        assert get_list_nesting_depth(Optional[int]) == 0


# ── get_field_raw_type ────────────────────────────────────────────────────


class TestGetFieldRawType:
    def test_plain_field(self):
        class M(Struct):
            age: int

        assert get_field_raw_type(M, "age") is int

    def test_annotated_field_unwraps(self):
        class M(Struct):
            name: Annotated[str, Unique()]

        assert get_field_raw_type(M, "name") is str

    def test_missing_field_returns_default(self):
        class M(Struct):
            x: int

        assert get_field_raw_type(M, "nope") is None

    def test_custom_default(self):
        class M(Struct):
            x: int

        sentinel = object()
        assert get_field_raw_type(M, "nope", default=sentinel) is sentinel

    def test_optional_field(self):
        class M(Struct):
            val: int | None = None

        result = get_field_raw_type(M, "val")
        # Should return the raw Union hint, not unwrap Optional
        assert result == int | None

    def test_annotated_optional(self):
        class M(Struct):
            val: Annotated[int | None, Unique()]

        # Unwraps Annotated layer, returns the inner Optional type
        assert get_field_raw_type(M, "val") == int | None

    def test_non_class_returns_default(self):
        assert get_field_raw_type(42, "x") is None  # type: ignore[arg-type]
