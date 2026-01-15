import datetime as dt
from msgspec import Struct

from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.types import IndexableField


class Nested(Struct):
    level1: str
    level2: int


class DeepNested(Struct):
    detail: Nested
    tags: list[str]


class TestResourceManagerIndexing:
    def test_extract_indexed_values_nested(self):
        """Test extraction of nested fields into structured dictionary."""

        # Setup ResourceManager with nested indexed fields
        meta_store = MemoryMetaStore()
        resource_store = MemoryResourceStore()
        storage = SimpleStorage(meta_store, resource_store)

        indexed_fields = [
            IndexableField(field_path="detail.level1", field_type=str),
            IndexableField(field_path="detail.level2", field_type=int),
            IndexableField(field_path="tags", field_type=list),
        ]

        manager = ResourceManager(
            resource_type=DeepNested, storage=storage, indexed_fields=indexed_fields
        )

        # Create sample data
        data = DeepNested(detail=Nested(level1="foo", level2=42), tags=["a", "b"])

        # 1. Test direct extraction method (private method)
        indexed_data = manager._extract_indexed_values(data)

        # Expect nested structure: {'detail': {'level1': 'foo', 'level2': 42}, 'tags': ['a', 'b']}
        assert indexed_data["detail"]["level1"] == "foo"
        assert indexed_data["detail"]["level2"] == 42
        assert indexed_data["tags"] == ["a", "b"]

        # Ensure it is NOT flat
        assert "detail.level1" not in indexed_data

        # 2. Test via create() to ensure metadata is saved correctly
        with manager.meta_provide(user="tester", now=dt.datetime.now()):
            info = manager.create(data)

        meta = manager.get_meta(info.resource_id)
        assert meta.indexed_data["detail"]["level1"] == "foo"
        assert meta.indexed_data["detail"]["level2"] == 42

    def test_extract_indexed_values_conflict_rollback(self):
        """Test conflict resolution when an existing value is not a dict (path collision)."""
        # This targets the specific retry/rollback logic in core.py lines 562-570

        class ConflictStruct(Struct):
            data: dict

        meta_store = MemoryMetaStore()
        resource_store = MemoryResourceStore()
        storage = SimpleStorage(meta_store, resource_store)

        # We need to trigger the condition:
        # 1. First field created a non-dict value at a path
        # 2. Second field tries to extend that path (treats it as intermediate node)
        # OR
        # 1. First field created a dict/path
        # 2. Second field tries to overwrite that dict with a non-dict value?
        # Let's look at the code:
        # for i, part in enumerate(parts[:-1]):
        #    ...
        #    if not isinstance(current, dict):
        #        current = {}
        #        if i > 0: ... rollback logic ...

        # Scenario:
        # Field 1: "a.b" = "leaf_value" (creates {"a": {"b": "leaf_value"}})
        # Field 2: "a.b.c" = "deep_value"
        # Processing Field 2:
        # - parts = ["a", "b", "c"]
        # - i=0, part="a". current=root. current["a"] is dict. OK. current = current["a"]
        # - i=1, part="b". current["b"] is "leaf_value" (NOT dict).
        # - Reaches "if not isinstance(current, dict):" block.
        # - i=1 (>0). Should trigger rollback logic.

        indexed_fields = [
            IndexableField(field_path="a.b", field_type=str),
            IndexableField(field_path="a.b.c", field_type=str),
        ]

        manager = ResourceManager(
            resource_type=ConflictStruct, storage=storage, indexed_fields=indexed_fields
        )

        # We manually use _extract_indexed_values.
        # Data structure doesn't strictly match schema because extract_by_path is flexible
        data = ConflictStruct(data={"a": {"b": "leaf_value", "extra": "info"}})

        # Mock _extract_by_path to return values matching our scenario
        # We can't easily mock valid object data that satisfies both paths simultaneously
        # for a real object if "a.b" is a string, then "a.b.c" is impossible.
        # BUT, indexed_fields don't have to exist in the source object simultaneously if we mock the extraction.
        # However, here manager uses its own _extract_by_path.

        # Let's manually inject values to provoke the issue.
        # Since _extract_indexed_values iterates over fields and calls _extract_by_path:

        original_extract = manager._extract_by_path

        def mock_extract(d, path):
            if path == "a.b":
                return "leaf_value"
            if path == "a.b.c":
                return "deep_value"
            return None

        manager._extract_by_path = mock_extract

        try:
            indexed_data = manager._extract_indexed_values(data)

            # What do we expect?
            # 1. "a.b" processed -> result["a"]["b"] = "leaf_value"
            # 2. "a.b.c" processed:
            #    - path "a" -> ok
            #    - path "b" -> found "leaf_value" (not dict) -> CONFLICT
            #    - entered rollback block
            #    - parent = root
            #    - for p in parts[:1] -> p="a". parent = parent["a"]
            #    - parent["b"] = {} (Overwrites "leaf_value")
            #    - current = parent["b"] ({})
            #    - loop continues (loop over parts[:-1] finished)
            #    - set final value: current["c"] = "deep_value"

            # So "leaf_value" is lost, replaced by object containing "c": "deep_value"

            assert indexed_data["a"]["b"]["c"] == "deep_value"
            assert not isinstance(indexed_data["a"]["b"], str)

        finally:
            manager._extract_by_path = original_extract

        """Test behavior when indexed fields conflict (one is prefix of another)."""
        # Note: Ideally schema design should prevent this, but let's see how code handles it.
        # If we index "detail" AND "detail.level1", it's tricky.

        class ConflictStruct(Struct):
            detail: dict

        meta_store = MemoryMetaStore()
        resource_store = MemoryResourceStore()
        storage = SimpleStorage(meta_store, resource_store)

        # Index "detail" (whole dict) AND "detail.id" (inside)
        # The current implementation might stick to the last one or merge?
        # Let's check what we implemented.
        # If "detail" is added first: indexed_data["detail"] = {...}
        # changes indexed_data["detail"] to be the value.
        # Then "detail.id" comes: parts=["detail", "id"].
        # current = indexed_data["detail"] -> which is the value from previous step (dict).
        # current["id"] = value.
        # So "detail" key will hold the dict from first step, modified by second step?

        indexed_fields = [
            IndexableField(field_path="detail", field_type=dict),
            IndexableField(field_path="detail.inner", field_type=str),
        ]

        manager = ResourceManager(
            resource_type=ConflictStruct, storage=storage, indexed_fields=indexed_fields
        )

        data = ConflictStruct(detail={"inner": "value", "other": "ignored"})

        # Execution order matters if we iterate list.
        # Current code iterates indexed_fields in order.

        indexed_data = manager._extract_indexed_values(data)

        # 1. process "detail": indexed_data["detail"] = {"inner": "value", "other": "ignored"}
        # 2. process "detail.inner":
        #    parts=["detail", "inner"]
        #    current = indexed_data
        #    part="detail". current["detail"] exists. is it dict? Yes (from step 1).
        #    current = current["detail"]
        #    current["inner"] = "value" (overwrites existing "value" with same "value")

        assert indexed_data["detail"]["inner"] == "value"
        assert indexed_data["detail"]["other"] == "ignored"
