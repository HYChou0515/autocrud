import pytest
from msgspec import Struct
from typing import Union
import datetime as dt
from autocrud.resource_manager.core import ResourceManager
from autocrud.resource_manager.storage_factory import MemoryStorageFactory


class TypeA(Struct, tag="a"):
    a_field: str


class TypeB(Struct, tag="b"):
    b_field: str


class MyResource(Struct):
    content: Union[TypeA, TypeB]


@pytest.fixture
def resource_manager():
    storage_factory = MemoryStorageFactory()
    storage = storage_factory.build("test_union")
    # Initialize ResourceManager with MyResource
    rm = ResourceManager(MyResource, storage=storage)
    return rm


@pytest.fixture(autouse=True)
def context(resource_manager):
    with resource_manager.meta_provide(
        user="test_user", now=dt.datetime.now(dt.timezone.utc)
    ):
        yield


def test_union_partial_basic(resource_manager):
    data_a = MyResource(content=TypeA(a_field="hello"))
    info_a = resource_manager.create(data_a)

    partial_data = resource_manager.get_partial(
        info_a.resource_id, info_a.revision_id, ["content/a_field"]
    )
    assert partial_data.content.a_field == "hello"


def test_union_partial_wrong_variant_field(resource_manager):
    """
    Test when we request a field that DOES NOT exist in the current variant,
    but exists in another variant of the Union.
    """
    data_b = MyResource(content=TypeB(b_field="world"))
    info_b = resource_manager.create(data_b)

    # Request field 'a_field' which exists in TypeA but NOT in TypeB.
    # The current data is TypeB.
    partial_data = resource_manager.get_partial(
        info_b.resource_id, info_b.revision_id, ["content/a_field"]
    )

    # partial_data.content should be of a partial TypeB type (because that's what the data is).
    # Since we didn't request any fields that exist in TypeB, it should be empty (but still tagged as 'b' effectively).

    # Verify that accessing 'a_field' raises AttributeError (because it's not in TypeB)
    # And accessing 'b_field' raises AttributeError (because we didn't request it)

    # Note: msgspec structs don't support hasattr nicely if they use slots/are standard structs.
    # But generated partials are structs.

    with pytest.raises(AttributeError):
        _ = partial_data.content.a_field

    with pytest.raises(AttributeError):
        _ = partial_data.content.b_field

    # We can verify it is indeed the PartialTypeB variant if we could check type or tag.
    # But partial structs are dynamically generated.
