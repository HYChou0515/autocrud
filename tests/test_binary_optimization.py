from typing import List, Optional, Dict, Any
from msgspec import Struct, UNSET
import pytest
import datetime as dt
from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.types import Binary
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore


class BinaryData(Struct):
    content: Binary
    name: str


class Menu(Struct):
    name: str
    icon: Optional[Binary] = None
    sub_menus: List["Menu"] = []


class UserWithBinary(Struct):
    id: str
    avatar: BinaryData
    files: List[BinaryData]
    metadata: Dict[str, BinaryData]
    optional_binary: Optional[BinaryData] = None


class MockBlobStore:
    def __init__(self):
        self.puts = []

    def put(self, data: bytes, *, content_type: Any = UNSET) -> Binary:
        self.puts.append(data)
        return Binary(file_id="mock_file_id", size=len(data), content_type=content_type)

    def get(self, file_id: str) -> Binary:
        return Binary(data=b"")


@pytest.fixture
def storage():
    resource_store = MemoryResourceStore(encoding="json")
    meta_store = MemoryMetaStore()
    return SimpleStorage(resource_store=resource_store, meta_store=meta_store)


def test_binary_traversal_optimization(storage):
    tracker_store = MockBlobStore()
    manager = ResourceManager(
        resource_type=UserWithBinary, storage=storage, blob_store=tracker_store
    )

    assert manager._binary_processor is not None, "Processor should be compiled"

    raw_content = b"testdata"

    # Test Dict Input
    input_dict = {
        "id": "1",
        "avatar": {"content": Binary(data=raw_content), "name": "avatar.png"},
        "files": [
            {"content": Binary(data=raw_content), "name": "file1.txt"},
            {"content": Binary(data=raw_content), "name": "file2.txt"},
        ],
        "metadata": {
            "key1": {"content": Binary(data=raw_content), "name": "meta1.dat"}
        },
    }

    manager._binary_processor.process(input_dict, tracker_store)
    assert len(tracker_store.puts) == 4

    # Test Struct Input
    tracker_store.puts = []
    input_struct = UserWithBinary(
        id="2",
        avatar=BinaryData(content=Binary(data=raw_content), name="avatar.png"),
        files=[
            BinaryData(content=Binary(data=raw_content), name="file1.txt"),
            BinaryData(content=Binary(data=raw_content), name="file2.txt"),
        ],
        metadata={
            "key1": BinaryData(content=Binary(data=raw_content), name="meta1.dat")
        },
    )

    manager._binary_processor.process(input_struct, tracker_store)
    assert len(tracker_store.puts) == 4


def test_recursive_struct_compilation(storage):
    tracker_store = MockBlobStore()
    # This should not raise RecursionError during init
    try:
        manager = ResourceManager(
            resource_type=Menu, storage=storage, blob_store=tracker_store
        )
    except RecursionError:
        pytest.fail(
            "ResourceManager init validation hit recursion error on recursive type"
        )

    assert manager._binary_processor is not None

    raw_content = b"icon"

    # Test recursive processing
    menu = Menu(
        name="root",
        icon=Binary(data=raw_content),
        sub_menus=[Menu(name="child", icon=Binary(data=raw_content))],
    )

    manager._binary_processor.process(menu, tracker_store)
    assert len(tracker_store.puts) == 2


def test_recursion_broken_structure(storage):
    # Test that we can handle recursive dicts without infinite loop if they are finite
    tracker_store = MockBlobStore()
    manager = ResourceManager(
        resource_type=Menu, storage=storage, blob_store=tracker_store
    )

    raw_content = b"icon"

    # Dict structure simulating recursive menu
    menu_dict = {
        "name": "root",
        "icon": Binary(data=raw_content),
        "sub_menus": [
            {"name": "child", "icon": Binary(data=raw_content), "sub_menus": []}
        ],
    }

    manager._binary_processor.process(menu_dict, tracker_store)
    assert len(tracker_store.puts) == 2


class LooseStruct(Struct):
    payload: Any


def test_binary_generic_coverage(storage):
    tracker_store = MockBlobStore()
    manager = ResourceManager(
        resource_type=LooseStruct, storage=storage, blob_store=tracker_store
    )

    # 1. Test Generic List (hits _process_binary_generic list branch)
    tracker_store.puts = []
    data_list = LooseStruct(payload=[Binary(data=b"1"), Binary(data=b"2")])
    processed_list = manager._binary_processor.process(data_list, tracker_store)

    assert len(tracker_store.puts) == 2
    assert processed_list.payload[0].file_id == "mock_file_id"
    assert processed_list.payload[0].data is UNSET

    # 2. Test Generic Dict (hits _process_binary_generic dict branch)
    tracker_store.puts = []
    data_dict = LooseStruct(payload={"k1": Binary(data=b"3"), "k2": Binary(data=b"4")})
    processed_dict = manager._binary_processor.process(data_dict, tracker_store)

    assert len(tracker_store.puts) == 2
    assert processed_dict.payload["k1"].file_id == "mock_file_id"

    # 3. Test Generic Struct (hits _process_binary_generic Struct branch)
    tracker_store.puts = []
    d = BinaryData(content=Binary(data=b"5"), name="n")
    data_struct = LooseStruct(payload=d)
    processed_struct = manager._binary_processor.process(data_struct, tracker_store)

    assert len(tracker_store.puts) == 1
    assert processed_struct.payload.content.file_id == "mock_file_id"

    # 4. Test No Changes (coverage for 'return data' paths)
    tracker_store.puts = []

    # List no change
    l_no_change = LooseStruct(payload=["a", "b"])
    res_l = manager._binary_processor.process(l_no_change, tracker_store)
    # Checks that original object is returned when no changes
    assert res_l.payload is l_no_change.payload

    # Dict no change
    d_no_change = LooseStruct(payload={"k": "v"})
    res_d = manager._binary_processor.process(d_no_change, tracker_store)
    assert res_d.payload is d_no_change.payload

    # Struct no change
    class Simple(Struct):
        x: int

    simple = Simple(x=1)
    s_wrapper = LooseStruct(payload=simple)
    res_s = manager._binary_processor.process(s_wrapper, tracker_store)
    assert res_s.payload is s_wrapper.payload


def test_public_api_binary_handling(storage):
    tracker_store = MockBlobStore()
    manager = ResourceManager(
        resource_type=UserWithBinary, storage=storage, blob_store=tracker_store
    )

    raw_content = b"public_api_content"

    # Test Create
    input_struct = UserWithBinary(
        id="create_test",
        avatar=BinaryData(content=Binary(data=raw_content), name="avatar.png"),
        files=[],
        metadata={},
    )

    # Should trigger binary processing via public create()
    # Need to provide meta context (user, now)
    with manager.meta_provide(user="test_user", now=dt.datetime.now(dt.timezone.utc)):
        info = manager.create(input_struct)

        # 1. Check side effect: blob stored
        assert len(tracker_store.puts) == 1, "Blob should be stored upon create"
        assert tracker_store.puts[0] == raw_content

        # 2. Check stored data via get() - file_id should be set, data should be None
        resource = manager.get(info.resource_id)
        saved_data = resource.data

        assert saved_data.avatar.content.file_id == "mock_file_id"
        assert saved_data.avatar.content.data is UNSET

        # Test Update
        new_content = b"updated_content"
        input_struct_update = UserWithBinary(
            id="create_test",
            avatar=BinaryData(content=Binary(data=new_content), name="avatar_v2.png"),
            files=[],
            metadata={},
        )

        manager.update(info.resource_id, input_struct_update)

        assert len(tracker_store.puts) == 2, "Blob should be stored upon update"
        assert tracker_store.puts[1] == new_content

        resource_updated = manager.get(info.resource_id)
        assert resource_updated.data.avatar.content.file_id == "mock_file_id"
        assert resource_updated.data.avatar.content.data is UNSET
        assert resource_updated.data.avatar.name == "avatar_v2.png"


def test_binary_restore(storage):
    class InMemoryBlobStore:
        def __init__(self):
            self.blobs = {}

        def put(self, data: bytes, *, content_type: Any = UNSET) -> Binary:
            file_id = f"hash-{len(self.blobs)}"
            self.blobs[file_id] = Binary(
                file_id=file_id, size=len(data), data=data, content_type=content_type
            )
            return Binary(file_id=file_id, size=len(data), content_type=content_type)

        def get(self, file_id: str) -> Binary:
            return self.blobs[file_id]

        def exists(self, file_id: str) -> bool:
            return file_id in self.blobs

    blob_store = InMemoryBlobStore()
    manager = ResourceManager(
        resource_type=UserWithBinary, storage=storage, blob_store=blob_store
    )

    raw_content = b"testdata-restore"

    # create object
    input_struct = UserWithBinary(
        id="restore-test",
        avatar=BinaryData(content=Binary(data=raw_content), name="avatar.png"),
        files=[],
        metadata={},
    )

    # Process converts data to file_id reference
    processed = manager._binary_processor.process(input_struct, blob_store)

    # Check it is processed (data is UNSET, file_id is set)
    assert isinstance(processed.avatar.content.data, type(UNSET))
    assert processed.avatar.content.file_id is not UNSET

    # Now restore
    restored = manager.restore_binary(processed)

    # Check it is restored
    assert restored.avatar.content.data == raw_content
    assert restored.avatar.content.file_id == processed.avatar.content.file_id


def test_binary_generic_restore(storage):
    # Tests _restore_generic by using LooseStruct where payload is Any
    class InMemoryBlobStore:
        def __init__(self):
            self.blobs = {}
            # Pre-populate a blob
            self.blobs["generic-id"] = Binary(
                file_id="generic-id", data=b"generic-restored"
            )

        def put(self, data: bytes, *, content_type: Any = UNSET) -> Binary:
            pass

        def get(self, file_id: str) -> Binary:
            return self.blobs[file_id]

    blob_store = InMemoryBlobStore()
    manager = ResourceManager(
        resource_type=LooseStruct, storage=storage, blob_store=blob_store
    )

    # 1. Test Generic List restore
    # Payload is a list containing a Binary with only file_id
    stored_binary = Binary(file_id="generic-id", data=UNSET)
    data_list = LooseStruct(payload=[stored_binary])

    restored_list = manager.restore_binary(data_list)
    assert restored_list.payload[0].data == b"generic-restored"

    # 2. Test Generic Dict restore
    data_dict = LooseStruct(payload={"key": stored_binary})
    restored_dict = manager.restore_binary(data_dict)
    assert restored_dict.payload["key"].data == b"generic-restored"

    # 3. Test Generic Struct restore (nested inside Any)
    # Since it's inside 'Any', compiled processor uses _restore_generic which checks isinstance(data, Struct)
    struct_data = BinaryData(content=stored_binary, name="test")
    data_struct_wrapper = LooseStruct(payload=struct_data)

    restored_struct = manager.restore_binary(data_struct_wrapper)
    assert restored_struct.payload.content.data == b"generic-restored"
