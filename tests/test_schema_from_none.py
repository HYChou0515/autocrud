"""Tests for migrating from unversioned (schema_version=None) data.

Issue 4: starting with a bare ``spec.add_model(User)`` stores
``schema_version=None``. Later upgrading to a versioned schema previously
required either rewriting the migration to special-case None or wrapping
the legacy data. We now accept ``from_ver=None`` directly on
``Schema.step()`` / ``Schema.plus()``.
"""

import io

import msgspec
import pytest
from msgspec import Struct

from specstar import Schema


class V1(Struct):
    name: str


class V2(Struct):
    name: str
    age: int


def _v1_to_v2(d: V1) -> V2:
    return V2(name=d.name, age=0)


def test_schema_step_accepts_none_from_ver():
    sch = Schema(V2, "v2").step(None, _v1_to_v2, source_type=V1)
    bio = io.BytesIO(msgspec.json.encode(V1(name="Alice")))
    out = sch.migrate(bio, None)
    assert out == V2(name="Alice", age=0)


def test_schema_plus_accepts_none_from_ver():
    sch = Schema(V2, "v2").plus(None, _v1_to_v2, source_type=V1)
    bio = io.BytesIO(msgspec.json.encode(V1(name="Bob")))
    out = sch.migrate(bio, None)
    assert out == V2(name="Bob", age=0)


def test_schema_no_path_from_none_raises_with_helpful_error():
    sch = Schema(V2, "v2").step("v1", _v1_to_v2, source_type=V1)
    bio = io.BytesIO(msgspec.json.encode(V1(name="Alice")))
    with pytest.raises(ValueError, match="No migration path from version None"):
        sch.migrate(bio, None)
