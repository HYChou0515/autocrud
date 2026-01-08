import datetime as dt
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from autocrud.resource_manager.basic import is_match_query
from autocrud.types import (
    DataSearchCondition,
    DataSearchGroup,
    DataSearchLogicOperator,
    DataSearchOperator,
    ResourceMeta,
    ResourceMetaSearchQuery,
    ResourceMetaSearchSort,
    ResourceMetaSortDirection,
    ResourceDataSearchSort,
    ResourceMetaSortKey,
)


@pytest.fixture
def my_tmpdir():
    """Fixture to provide a temporary directory for testing."""
    import tempfile

    with tempfile.TemporaryDirectory(dir="./") as d:
        yield Path(d)


@pytest.mark.parametrize(
    "meta_store_type",
    [
        "memory",
        "sql3-mem",
        "sql3-file",
        "memory-pg",
        "redis",
        "redis-pg",
        "postgres",
        "df",
    ],
)
class TestComprehensiveDataSearch:
    """Comprehensive tests for IMetaStore.iter_search covering all operators and types."""

    @pytest.fixture(autouse=True)
    def setup_method(self, meta_store_type, my_tmpdir):
        self.meta_store = self._get_meta_store(meta_store_type, my_tmpdir)
        self.sample_data = self._create_sample_data(self.meta_store)

    def _get_meta_store(self, store_type: str, tmpdir):
        """Get meta store instance."""
        from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
        from autocrud.resource_manager.meta_store.sqlite3 import (
            FileSqliteMetaStore,
            MemorySqliteMetaStore,
        )

        if store_type == "memory":
            return MemoryMetaStore(encoding="msgpack")
        if store_type == "sql3-mem":
            return MemorySqliteMetaStore(encoding="msgpack")
        if store_type == "sql3-file":
            return FileSqliteMetaStore(
                db_filepath=tmpdir / "test_data_search_comp.db",
                encoding="msgpack",
            )
        if store_type == "df":
            try:
                from autocrud.resource_manager.meta_store.df import DFMemoryMetaStore

                return DFMemoryMetaStore(encoding="msgpack")
            except ImportError as e:
                pytest.skip(f"Pandas not available: {e}")

        if store_type == "memory-pg":
            import psycopg2

            from autocrud.resource_manager.meta_store.fast_slow import FastSlowMetaStore
            from autocrud.resource_manager.meta_store.postgres import PostgresMetaStore

            # Setup PostgreSQL connection
            pg_dsn = "postgresql://admin:password@localhost:5432/your_database"
            try:
                # Reset the test database
                pg_conn = psycopg2.connect(pg_dsn)
                with pg_conn.cursor() as cur:
                    cur.execute("DROP TABLE IF EXISTS resource_meta;")
                    pg_conn.commit()
                pg_conn.close()

                return FastSlowMetaStore(
                    fast_store=MemoryMetaStore(encoding="msgpack"),
                    slow_store=PostgresMetaStore(pg_dsn=pg_dsn, encoding="msgpack"),
                )
            except Exception as e:
                pytest.skip(f"PostgreSQL not available: {e}")
        elif store_type == "postgres":
            import psycopg2

            from autocrud.resource_manager.meta_store.postgres import PostgresMetaStore

            # Setup PostgreSQL connection
            pg_dsn = "postgresql://admin:password@localhost:5432/your_database"
            try:
                # Reset the test database
                pg_conn = psycopg2.connect(pg_dsn)
                with pg_conn.cursor() as cur:
                    cur.execute("DROP TABLE IF EXISTS resource_meta;")
                    pg_conn.commit()
                pg_conn.close()

                return PostgresMetaStore(pg_dsn=pg_dsn, encoding="msgpack")
            except Exception as e:
                pytest.skip(f"PostgreSQL not available: {e}")
        elif store_type == "redis":
            import redis

            from autocrud.resource_manager.meta_store.redis import RedisMetaStore

            # Setup Redis connection
            redis_url = "redis://localhost:6379/0"
            try:
                # Reset the test Redis database
                client = redis.Redis.from_url(redis_url)
                client.flushall()
                client.close()

                return RedisMetaStore(
                    redis_url=redis_url,
                    encoding="msgpack",
                    prefix=str(tmpdir).rsplit("/", 1)[-1],
                )
            except Exception as e:
                pytest.skip(f"Redis not available: {e}")
        elif store_type == "redis-pg":
            import psycopg2
            import redis

            from autocrud.resource_manager.meta_store.fast_slow import FastSlowMetaStore
            from autocrud.resource_manager.meta_store.postgres import PostgresMetaStore
            from autocrud.resource_manager.meta_store.redis import RedisMetaStore

            # Setup Redis and PostgreSQL connections
            redis_url = "redis://localhost:6379/0"
            pg_dsn = "postgresql://admin:password@localhost:5432/your_database"

            try:
                # Reset the test Redis database
                client = redis.Redis.from_url(redis_url)
                client.flushall()
                client.close()

                # Reset the test PostgreSQL database
                pg_conn = psycopg2.connect(pg_dsn)
                with pg_conn.cursor() as cur:
                    cur.execute("DROP TABLE IF EXISTS resource_meta;")
                    pg_conn.commit()
                pg_conn.close()

                return FastSlowMetaStore(
                    fast_store=RedisMetaStore(
                        redis_url=redis_url,
                        encoding="msgpack",
                        prefix=str(tmpdir).rsplit("/", 1)[-1],
                    ),
                    slow_store=PostgresMetaStore(pg_dsn=pg_dsn, encoding="msgpack"),
                )
            except Exception as e:
                pytest.skip(f"Redis or PostgreSQL not available: {e}")
        else:
            raise ValueError(f"Unsupported store_type: {store_type}")

    def _create_sample_data(self, meta_store):
        base_time = dt.datetime(2023, 1, 1, 12, 0, 0, tzinfo=ZoneInfo("UTC"))

        # Data set designed to test various conditions
        # 1. String: "apple", "banana", "cherry", "date"
        # 2. Int: 10, 20, 30, 40
        # 3. Float: 1.1, 2.2, 3.3, 4.4
        # 4. Bool: True, False, True, False
        # 5. List[str]: ["a", "b"], ["b", "c"], ["c", "d"], ["d", "e"]
        # 6. List[int]: [1, 2], [2, 3], [3, 4], [4, 5]

        data_list = [
            {
                "id": "1",
                "str": "apple",
                "int": 10,
                "float": 1.1,
                "bool": True,
                "list_str": ["a", "b"],
                "list_int": [1, 2],
            },
            {
                "id": "2",
                "str": "banana",
                "int": 20,
                "float": 2.2,
                "bool": False,
                "list_str": ["b", "c"],
                "list_int": [2, 3],
            },
            {
                "id": "3",
                "str": "cherry",
                "int": 30,
                "float": 3.3,
                "bool": True,
                "list_str": ["c", "d"],
                "list_int": [3, 4],
            },
            {
                "id": "4",
                "str": "date",
                "int": 40,
                "float": 4.4,
                "bool": False,
                "list_str": ["d", "e"],
                "list_int": [4, 5],
            },
        ]

        metas = []
        for i, d in enumerate(data_list):
            meta = ResourceMeta(
                current_revision_id=f"rev_{d['id']}",
                resource_id=str(uuid.uuid4()),
                total_revision_count=1,
                created_time=base_time + dt.timedelta(minutes=i),
                updated_time=base_time + dt.timedelta(minutes=i),
                created_by="test_user",
                updated_by="test_user",
                is_deleted=False,
                indexed_data=d,
            )
            meta_store[meta.resource_id] = meta
            metas.append(meta)

        return metas

    def _assert_search_results(self, conditions, allow_empty=False):
        """Run search and verify results against in-memory filtering."""
        query = ResourceMetaSearchQuery(
            conditions=conditions,
            limit=100,
            offset=0,
        )

        # 1. Get actual results from meta store
        results = list(self.meta_store.iter_search(query))
        result_ids = sorted([m.indexed_data["id"] for m in results])

        # 2. Calculate expected results using Python filtering (ground truth)
        expected_ids = []
        for meta in self.sample_data:
            if is_match_query(meta, query):
                expected_ids.append(meta.indexed_data["id"])
        expected_ids.sort()

        if not allow_empty:
            assert result_ids, (
                "Result set is empty, indicating this is a bad test case."
            )
        assert result_ids == expected_ids, f"Failed for conditions: {conditions}"

    # --- Equals ---

    def test_equals_string(self):
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="str", operator=DataSearchOperator.equals, value="banana"
                )
            ]
        )

    def test_equals_int(self):
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="int", operator=DataSearchOperator.equals, value=20
                )
            ]
        )

    def test_equals_float(self):
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="float", operator=DataSearchOperator.equals, value=3.3
                )
            ]
        )

    def test_equals_bool(self):
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="bool", operator=DataSearchOperator.equals, value=True
                )
            ]
        )

    # --- Not Equals ---

    def test_not_equals_string(self):
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="str",
                    operator=DataSearchOperator.not_equals,
                    value="banana",
                )
            ]
        )

    def test_not_equals_int(self):
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="int", operator=DataSearchOperator.not_equals, value=20
                )
            ]
        )

    # --- Greater Than ---

    def test_greater_than_int(self):
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="int", operator=DataSearchOperator.greater_than, value=20
                )
            ]
        )

    def test_greater_than_float(self):
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="float",
                    operator=DataSearchOperator.greater_than,
                    value=2.2,
                )
            ]
        )

    # --- Greater Than Or Equal ---

    def test_greater_than_or_equal_int(self):
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="int",
                    operator=DataSearchOperator.greater_than_or_equal,
                    value=20,
                )
            ]
        )

    # --- Less Than ---

    def test_less_than_int(self):
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="int", operator=DataSearchOperator.less_than, value=30
                )
            ]
        )

    # --- Less Than Or Equal ---

    def test_less_than_or_equal_int(self):
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="int",
                    operator=DataSearchOperator.less_than_or_equal,
                    value=30,
                )
            ]
        )

    # --- Contains ---

    def test_contains_string_substring(self):
        # "apple", "banana", "cherry", "date"
        # "an" is in "banana"
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="str", operator=DataSearchOperator.contains, value="an"
                )
            ]
        )

    def test_contains_list_str(self):
        # ["a", "b"], ["b", "c"], ["c", "d"], ["d", "e"]
        # "b" is in 1 and 2
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="list_str",
                    operator=DataSearchOperator.contains,
                    value="b",
                )
            ]
        )

    def test_contains_list_int(self):
        # [1, 2], [2, 3], [3, 4], [4, 5]
        # 3 is in 2 and 3
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="list_int", operator=DataSearchOperator.contains, value=3
                )
            ]
        )

    # --- Starts With ---

    def test_starts_with_string(self):
        # "apple", "banana", "cherry", "date"
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="str",
                    operator=DataSearchOperator.starts_with,
                    value="ba",
                )
            ]
        )

    # --- Ends With ---

    def test_ends_with_string(self):
        # "apple", "banana", "cherry", "date"
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="str", operator=DataSearchOperator.ends_with, value="na"
                )
            ]
        )

    # --- In List ---

    def test_in_list_string(self):
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="str",
                    operator=DataSearchOperator.in_list,
                    value=["apple", "date"],
                )
            ]
        )

    def test_in_list_int(self):
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="int",
                    operator=DataSearchOperator.in_list,
                    value=[10, 30],
                )
            ]
        )

    # --- Not In List ---

    def test_not_in_list_string(self):
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="str",
                    operator=DataSearchOperator.not_in_list,
                    value=["apple", "date"],
                )
            ]
        )

    # --- Logic Operators ---

    def test_logic_and(self):
        # (int > 10) AND (bool == True)
        # 1: int=10 (False), bool=True
        # 2: int=20 (True), bool=False
        # 3: int=30 (True), bool=True -> Match
        # 4: int=40 (True), bool=False
        self._assert_search_results(
            [
                DataSearchGroup(
                    operator=DataSearchLogicOperator.and_op,
                    conditions=[
                        DataSearchCondition(
                            field_path="int",
                            operator=DataSearchOperator.greater_than,
                            value=10,
                        ),
                        DataSearchCondition(
                            field_path="bool",
                            operator=DataSearchOperator.equals,
                            value=True,
                        ),
                    ],
                )
            ]
        )

    def test_logic_or(self):
        # (str == "apple") OR (str == "date")
        # 1: apple -> Match
        # 4: date -> Match
        self._assert_search_results(
            [
                DataSearchGroup(
                    operator=DataSearchLogicOperator.or_op,
                    conditions=[
                        DataSearchCondition(
                            field_path="str",
                            operator=DataSearchOperator.equals,
                            value="apple",
                        ),
                        DataSearchCondition(
                            field_path="str",
                            operator=DataSearchOperator.equals,
                            value="date",
                        ),
                    ],
                )
            ]
        )

    def test_logic_not(self):
        # NOT (int > 20)
        # 1: 10 -> Match
        # 2: 20 -> Match
        # 3: 30 -> False
        # 4: 40 -> False
        self._assert_search_results(
            [
                DataSearchGroup(
                    operator=DataSearchLogicOperator.not_op,
                    conditions=[
                        DataSearchCondition(
                            field_path="int",
                            operator=DataSearchOperator.greater_than,
                            value=20,
                        )
                    ],
                )
            ]
        )

    def test_nested_logic(self):
        # (int > 10) AND ((str == "banana") OR (str == "cherry"))
        # 1: int=10 -> False
        # 2: int=20, str=banana -> Match
        # 3: int=30, str=cherry -> Match
        # 4: int=40, str=date -> False
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="int",
                    operator=DataSearchOperator.greater_than,
                    value=10,
                ),
                DataSearchGroup(
                    operator=DataSearchLogicOperator.or_op,
                    conditions=[
                        DataSearchCondition(
                            field_path="str",
                            operator=DataSearchOperator.equals,
                            value="banana",
                        ),
                        DataSearchCondition(
                            field_path="str",
                            operator=DataSearchOperator.equals,
                            value="cherry",
                        ),
                    ],
                ),
            ]
        )

    def test_is_null(self):
        # Add a record with null values and missing keys
        null_data = {
            "id": "5",
            "str": None,
            # "int" is missing
            "float": 5.5,
            "bool": None,
        }
        meta = ResourceMeta(
            current_revision_id="rev_5",
            resource_id=str(uuid.uuid4()),
            total_revision_count=1,
            created_time=dt.datetime.now(dt.timezone.utc),
            updated_time=dt.datetime.now(dt.timezone.utc),
            created_by="test_user",
            updated_by="test_user",
            is_deleted=False,
            indexed_data=null_data,
        )
        self.meta_store[meta.resource_id] = meta
        self.sample_data.append(meta)

        # Add another record where int is Explicitly None
        explicit_null_data = {
            "id": "5_explicit",
            "int": None,
        }
        meta_explicit = ResourceMeta(
            current_revision_id="rev_5_explicit",
            resource_id=str(uuid.uuid4()),
            total_revision_count=1,
            created_time=dt.datetime.now(dt.timezone.utc),
            updated_time=dt.datetime.now(dt.timezone.utc),
            created_by="test_user",
            updated_by="test_user",
            is_deleted=False,
            indexed_data=explicit_null_data,
        )
        self.meta_store[meta_explicit.resource_id] = meta_explicit
        self.sample_data.append(meta_explicit)

        # Test is_null = True (should match id=5 for "str")
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="str",
                    operator=DataSearchOperator.is_null,
                    value=True,
                )
            ]
        )

        # Test is_null = True
        # "int" is missing in id=5. Strict is_null requires existence.
        # "int" is None in id=5_explicit.
        # So this should match ONLY id=5_explicit.
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="int",
                    operator=DataSearchOperator.is_null,
                    value=True,
                )
            ]
        )

        # Test is_null = False (should match id=1,2,3,4 for "str")
        # id=5 has str=None. So is_null(False) should not match id=5.
        # id=5_explicit missing str. Strict is_null(False) requires existence. So it won't match 5_explicit.
        # id=1,2,3,4 have str="apple", "banana", etc. So they match.
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="str",
                    operator=DataSearchOperator.is_null,
                    value=False,
                )
            ]
        )

    def test_exists_and_isna(self):
        # Add a record with null values and missing keys
        data_6 = {
            "id": "6",
            "present_val": "value",
            "present_null": None,
            # "missing_key" is missing
        }
        meta = ResourceMeta(
            current_revision_id="rev_6",
            resource_id=str(uuid.uuid4()),
            total_revision_count=1,
            created_time=dt.datetime.now(dt.timezone.utc),
            updated_time=dt.datetime.now(dt.timezone.utc),
            created_by="test_user",
            updated_by="test_user",
            is_deleted=False,
            indexed_data=data_6,
        )
        self.meta_store[meta.resource_id] = meta
        self.sample_data.append(meta)

        # 1. Test exists = True
        # Should match "present_val" (id=6) and "present_null" (id=6)
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="present_val",
                    operator=DataSearchOperator.exists,
                    value=True,
                )
            ]
        )
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="present_null",
                    operator=DataSearchOperator.exists,
                    value=True,
                )
            ]
        )

        # 2. Test exists = False
        # Should match id=6 for "missing_key"
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="missing_key",
                    operator=DataSearchOperator.exists,
                    value=False,
                )
            ]
        )

        # 3. Test isna = True (missing or null)
        # Should match id=6 for "present_null" (is null)
        # Should match id=6 for "missing_key" (missing)
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="present_null",
                    operator=DataSearchOperator.isna,
                    value=True,
                )
            ]
        )
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="missing_key",
                    operator=DataSearchOperator.isna,
                    value=True,
                )
            ]
        )

        # 4. Test isna = False (exists and not null)
        # Should match id=6 for "present_val"
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="present_val",
                    operator=DataSearchOperator.isna,
                    value=False,
                )
            ]
        )

    def test_strict_missing_behavior(self):
        # Verify that value comparisons on missing keys return False
        # We need to verify that missing keys DO NOT match, while present keys DO match.

        # 1. Record with missing key
        data_missing = {
            "id": "7_missing",
            # "target_val" is missing
        }
        meta_missing = ResourceMeta(
            current_revision_id="rev_7_missing",
            resource_id=str(uuid.uuid4()),
            total_revision_count=1,
            created_time=dt.datetime.now(dt.timezone.utc),
            updated_time=dt.datetime.now(dt.timezone.utc),
            created_by="test_user",
            updated_by="test_user",
            is_deleted=False,
            indexed_data=data_missing,
        )
        self.meta_store[meta_missing.resource_id] = meta_missing
        self.sample_data.append(meta_missing)

        # 2. Record with key present
        data_present = {
            "id": "7_present",
            "target_val": 20,  # int
        }
        meta_present = ResourceMeta(
            current_revision_id="rev_7_present",
            resource_id=str(uuid.uuid4()),
            total_revision_count=1,
            created_time=dt.datetime.now(dt.timezone.utc),
            updated_time=dt.datetime.now(dt.timezone.utc),
            created_by="test_user",
            updated_by="test_user",
            is_deleted=False,
            indexed_data=data_present,
        )
        self.meta_store[meta_present.resource_id] = meta_present
        self.sample_data.append(meta_present)

        # 1. Not Equals
        # target_val != 999
        # "missing" should be False (strict).
        # "present" (20) != 999 is True.
        # Should match ONLY "7_present".
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="target_val",
                    operator=DataSearchOperator.not_equals,
                    value=999,
                )
            ]
        )

        # 2. Not In List
        # target_val not in [1, 2]
        # "missing" -> False
        # "present" (20) -> True
        # Should match ONLY "7_present".
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="target_val",
                    operator=DataSearchOperator.not_in_list,
                    value=[1, 2],
                )
            ]
        )

        # 3. Greater Than
        # target_val > 10
        # "missing" -> False
        # "present" (20) -> True
        # Should match ONLY "7_present".
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="target_val",
                    operator=DataSearchOperator.greater_than,
                    value=10,
                )
            ]
        )

    def test_conditions_meta_fields(self):
        """Test searching meta fields using the new `conditions` field."""
        # All sample data has created_by="test_user"
        query = ResourceMetaSearchQuery(
            conditions=[
                DataSearchCondition(
                    field_path="created_by",
                    operator=DataSearchOperator.equals,
                    value="test_user",
                )
            ],
            limit=100,
        )
        results = list(self.meta_store.iter_search(query))
        assert len(results) >= 4
        for meta in results:
            assert meta.created_by == "test_user"

        # Test non-matching
        query_none = ResourceMetaSearchQuery(
            conditions=[
                DataSearchCondition(
                    field_path="created_by",
                    operator=DataSearchOperator.equals,
                    value="non_existent_user",
                )
            ],
            limit=100,
        )
        results_none = list(self.meta_store.iter_search(query_none))
        assert len(results_none) == 0

        # Test starts_with on meta field
        query_starts = ResourceMetaSearchQuery(
            conditions=[
                DataSearchCondition(
                    field_path="created_by",
                    operator=DataSearchOperator.starts_with,
                    value="test",
                )
            ],
            limit=100,
        )
        results_starts = list(self.meta_store.iter_search(query_starts))
        assert len(results_starts) >= 4

    def test_conditions_mixed_fields(self):
        """Test searching both meta and data fields using `conditions`."""
        # created_by="test_user" AND str="apple"
        query = ResourceMetaSearchQuery(
            conditions=[
                DataSearchCondition(
                    field_path="created_by",
                    operator=DataSearchOperator.equals,
                    value="test_user",
                ),
                DataSearchCondition(
                    field_path="str",
                    operator=DataSearchOperator.equals,
                    value="apple",
                ),
            ],
            limit=100,
        )
        results = list(self.meta_store.iter_search(query))
        assert len(results) == 1
        assert results[0].indexed_data["str"] == "apple"
        assert results[0].created_by == "test_user"

    def test_conditions_data_fields_replacement(self):
        """Test that `conditions` works as a replacement for `data_conditions`."""
        # Same as test_equals_string but using conditions
        query = ResourceMetaSearchQuery(
            conditions=[
                DataSearchCondition(
                    field_path="str",
                    operator=DataSearchOperator.equals,
                    value="banana",
                )
            ],
            limit=100,
        )
        results = list(self.meta_store.iter_search(query))
        assert len(results) == 1
        assert results[0].indexed_data["str"] == "banana"

    # --- Sorting ---

    def test_sort_int_asc(self):
        query = ResourceMetaSearchQuery(
            sorts=[
                ResourceDataSearchSort(
                    field_path="int",
                    direction=ResourceMetaSortDirection.ascending,
                )
            ],
            limit=100,
        )
        results = list(self.meta_store.iter_search(query))
        ids = [m.indexed_data["id"] for m in results]
        # 10, 20, 30, 40 -> id 1, 2, 3, 4
        assert ids == ["1", "2", "3", "4"]

    def test_sort_int_desc(self):
        query = ResourceMetaSearchQuery(
            sorts=[
                ResourceDataSearchSort(
                    field_path="int",
                    direction=ResourceMetaSortDirection.descending,
                )
            ],
            limit=100,
        )
        results = list(self.meta_store.iter_search(query))
        ids = [m.indexed_data["id"] for m in results]
        # 40, 30, 20, 10 -> id 4, 3, 2, 1
        assert ids == ["4", "3", "2", "1"]

    def test_sort_meta_field_desc(self):
        # created_time is set to base_time + i minutes.
        # i=0(id1), i=1(id2), i=2(id3), i=3(id4)
        # DESC -> 4, 3, 2, 1
        query = ResourceMetaSearchQuery(
            sorts=[
                ResourceMetaSearchSort(
                    key=ResourceMetaSortKey.created_time,
                    direction=ResourceMetaSortDirection.descending,
                )
            ],
            limit=100,
        )
        results = list(self.meta_store.iter_search(query))
        ids = [m.indexed_data["id"] for m in results]
        assert ids == ["4", "3", "2", "1"]

    # --- Pagination ---

    def test_pagination_limit(self):
        query = ResourceMetaSearchQuery(
            sorts=[
                ResourceDataSearchSort(
                    field_path="int",
                    direction=ResourceMetaSortDirection.ascending,
                )
            ],
            limit=2,
            offset=0,
        )
        results = list(self.meta_store.iter_search(query))
        ids = [m.indexed_data["id"] for m in results]
        assert ids == ["1", "2"]

    def test_pagination_offset(self):
        query = ResourceMetaSearchQuery(
            sorts=[
                ResourceDataSearchSort(
                    field_path="int",
                    direction=ResourceMetaSortDirection.ascending,
                )
            ],
            limit=2,
            offset=2,
        )
        results = list(self.meta_store.iter_search(query))
        ids = [m.indexed_data["id"] for m in results]
        assert ids == ["3", "4"]

    # --- Regex ---

    def test_regex_match(self):
        # Only strings support regex
        # "banana" matches "^ban.*"
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="str",
                    operator=DataSearchOperator.regex,
                    value="^ban.*",
                )
            ]
        )

    def test_regex_other_match(self):
        # Add a record that matches a different regex
        data_xyz = {
            "id": "xyz_1",
            "str": "xyz_start",
        }
        meta_xyz = ResourceMeta(
            current_revision_id="rev_xyz",
            resource_id=str(uuid.uuid4()),
            total_revision_count=1,
            created_time=dt.datetime.now(dt.timezone.utc),
            updated_time=dt.datetime.now(dt.timezone.utc),
            created_by="test_user",
            updated_by="test_user",
            is_deleted=False,
            indexed_data=data_xyz,
        )
        self.meta_store[meta_xyz.resource_id] = meta_xyz
        self.sample_data.append(meta_xyz)

        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="str",
                    operator=DataSearchOperator.regex,
                    value="^xyz.*",
                )
            ]
        )

    # --- Meta Fields via conditions ---

    def test_meta_created_time_gt(self):
        """Test filtering by created_time using generic conditions."""
        # created_time is base_time + i minutes.
        # base = 12:00.
        # id=1: 12:00, id=2: 12:01, id=3: 12:02, id=4: 12:03
        # > 12:01 -> id 3, 4
        limit_time = self.sample_data[1].created_time

        query = ResourceMetaSearchQuery(
            conditions=[
                DataSearchCondition(
                    field_path="created_time",
                    operator=DataSearchOperator.greater_than,
                    value=limit_time,
                )
            ],
            limit=100,
        )
        # We cannot use _assert_search_results here directly if it doesn't support
        # overriding the query, but wait, _assert_search_results creates the query internally.
        # _assert_search_results accepts 'conditions'.
        # Let's use _assert_search_results directly which is cleaner and tests the comparison logic too.

        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="created_time",
                    operator=DataSearchOperator.greater_than,
                    value=limit_time,
                )
            ]
        )

    def test_meta_resource_id_in_list(self):
        """Test filtering resource_id using in_list."""
        target_ids = [self.sample_data[0].resource_id, self.sample_data[3].resource_id]

        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="resource_id",
                    operator=DataSearchOperator.in_list,
                    value=target_ids,
                )
            ]
        )

    def test_meta_is_deleted_eq(self):
        """Test filtering is_deleted."""
        # By default all are False.
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="is_deleted",
                    operator=DataSearchOperator.equals,
                    value=False,
                )
            ]
        )

    # --- Special Characters ---

    def test_special_characters_string(self):
        """Test strings with quotes, spaces, special chars."""
        special_str = "foo ' bar \" baz % ; --"
        data_special = {"id": "special_1", "str": special_str, "int": 999}
        meta = ResourceMeta(
            current_revision_id="rev_special_1",
            resource_id=str(uuid.uuid4()),
            total_revision_count=1,
            created_time=dt.datetime.now(dt.timezone.utc),
            updated_time=dt.datetime.now(dt.timezone.utc),
            created_by="special_user",
            updated_by="special_user",
            is_deleted=False,
            indexed_data=data_special,
        )
        self.meta_store[meta.resource_id] = meta
        self.sample_data.append(meta)

        # 1. Exact match
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="str",
                    operator=DataSearchOperator.equals,
                    value=special_str,
                )
            ]
        )

        # 2. Contains with quote
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="str",
                    operator=DataSearchOperator.contains,
                    value="' bar",
                )
            ]
        )

    # --- Complex Mixed Logic ---

    def test_complex_mixed_logic_and_nested_or(self):
        """
        (created_by = 'test_user') AND (
            (int >= 30) OR (str starts_with 'app')
        )
        """
        # test_user is true for all original 4
        # int >= 30: id 3 (30), id 4 (40)
        # str starts_with 'app': id 1 (apple)
        # expected: 1, 3, 4

        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="created_by",
                    operator=DataSearchOperator.equals,
                    value="test_user",
                ),
                DataSearchGroup(
                    operator=DataSearchLogicOperator.or_op,
                    conditions=[
                        DataSearchCondition(
                            field_path="int",
                            operator=DataSearchOperator.greater_than_or_equal,
                            value=30,
                        ),
                        DataSearchCondition(
                            field_path="str",
                            operator=DataSearchOperator.starts_with,
                            value="app",
                        ),
                    ],
                ),
            ]
        )

    # --- Additional Meta Field Tests ---

    def test_meta_updated_time_ops(self):
        """Test comparisons on updated_time."""
        # updated_time is same as created_time in sample data: base + i minutes
        # id=1 (base+0), id=2 (base+1), id=3 (base+2), id=4 (base+3)
        target_time = self.sample_data[2].updated_time  # id=3

        # 1. Less Than Strict
        # < id=3 => id=1, 2
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="updated_time",
                    operator=DataSearchOperator.less_than,
                    value=target_time,
                )
            ]
        )

        # 2. Less Than Or Equal
        # <= id=3 => id=1, 2, 3
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="updated_time",
                    operator=DataSearchOperator.less_than_or_equal,
                    value=target_time,
                )
            ]
        )

        # 3. Greater Than Or Equal
        # >= id=3 => id=3, 4
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="updated_time",
                    operator=DataSearchOperator.greater_than_or_equal,
                    value=target_time,
                )
            ]
        )

        # 4. Not Equals
        # != id=3 => id=1, 2, 4
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="updated_time",
                    operator=DataSearchOperator.not_equals,
                    value=target_time,
                )
            ]
        )

    def test_meta_updated_by_ops(self):
        """Test operators on updated_by."""
        # Current sample data all have "test_user".
        # Let's add a record with diff updated_by.

        meta = ResourceMeta(
            current_revision_id="rev_diff_user",
            resource_id=str(uuid.uuid4()),
            total_revision_count=1,
            created_time=dt.datetime.now(dt.timezone.utc),
            updated_time=dt.datetime.now(dt.timezone.utc),
            created_by="admin",
            updated_by="admin_user",
            is_deleted=False,
            indexed_data={"id": "diff_user", "val": 100},
        )
        self.meta_store[meta.resource_id] = meta
        self.sample_data.append(meta)

        # 1. Contains
        # "admin_user" contains "min"
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="updated_by",
                    operator=DataSearchOperator.contains,
                    value="min",
                )
            ]
        )

        # 2. Ends With
        # "admin_user" ends with "user"
        # "test_user" ends with "user"
        # So it should match all 5 records.
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="updated_by",
                    operator=DataSearchOperator.ends_with,
                    value="user",
                )
            ]
        )

        # 3. Regex
        # starts with admin
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="updated_by",
                    operator=DataSearchOperator.regex,
                    value="^admin.*",
                )
            ]
        )

        # 4. Not In List
        # not in ["test_user"] => match "admin_user"
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="updated_by",
                    operator=DataSearchOperator.not_in_list,
                    value=["test_user"],
                )
            ]
        )

    def test_meta_null_checks(self):
        """Test is_null, exists, isna on meta fields."""
        # schema_version is None by default in sample data.
        # Let's add one with schema_version set.

        meta_ver = ResourceMeta(
            current_revision_id="rev_ver",
            resource_id=str(uuid.uuid4()),
            total_revision_count=1,
            created_time=dt.datetime.now(dt.timezone.utc),
            updated_time=dt.datetime.now(dt.timezone.utc),
            created_by="test_user",
            updated_by="test_user",
            is_deleted=False,
            schema_version="v1.0",
            indexed_data={"id": "ver_1"},
        )
        self.meta_store[meta_ver.resource_id] = meta_ver
        self.sample_data.append(meta_ver)

        # 1. is_null = True (should match the default ones, i.e. 4 records)
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="schema_version",
                    operator=DataSearchOperator.is_null,
                    value=True,
                )
            ]
        )

        # 2. is_null = False (should match id="ver_1")
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="schema_version",
                    operator=DataSearchOperator.is_null,
                    value=False,
                )
            ]
        )

        # 3. exists = True
        # Meta fields always exist as attributes, but we check if logic holds.
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="updated_by",
                    operator=DataSearchOperator.exists,
                    value=True,
                )
            ]
        )

        # 4. isna = True (None or Missing)
        # schema_version is None for 4 records.
        self._assert_search_results(
            [
                DataSearchCondition(
                    field_path="schema_version",
                    operator=DataSearchOperator.isna,
                    value=True,
                )
            ]
        )

    def test_logic_not_sub_conditions(self):
        """Test NOT operator with a Group (sub-conditions)."""
        # NOT ( int > 20 AND str startswith 'ch' )
        # id=3: int=30, str=cherry. (30>20 AND cherry starts ch) is TRUE. NOT->FALSE.
        # others: FALSE. NOT->TRUE.
        # So we expect id 1, 2, 4.

        self._assert_search_results(
            [
                DataSearchGroup(
                    operator=DataSearchLogicOperator.not_op,
                    conditions=[
                        DataSearchGroup(  # Nested AND
                            operator=DataSearchLogicOperator.and_op,
                            conditions=[
                                DataSearchCondition(
                                    field_path="int",
                                    operator=DataSearchOperator.greater_than,
                                    value=20,
                                ),
                                DataSearchCondition(
                                    field_path="str",
                                    operator=DataSearchOperator.starts_with,
                                    value="ch",
                                ),
                            ],
                        )
                    ],
                )
            ]
        )

    def test_search_legacy_fields(self):
        """Test search using legacy fields directly on ResourceMetaSearchQuery."""
        # 1. is_deleted
        # All sample data has is_deleted=False
        q = ResourceMetaSearchQuery(is_deleted=True, limit=100)
        results = list(self.meta_store.iter_search(q))
        assert len(results) == 0

        q = ResourceMetaSearchQuery(is_deleted=False, limit=100)
        results = list(self.meta_store.iter_search(q))
        assert len(results) == len(self.sample_data)

        # 2. created_time range
        # sample_data created times are separated by 1 minute
        base_time = self.sample_data[0].created_time
        # Select first 2 items
        end_time = base_time + dt.timedelta(minutes=1, seconds=30)
        q = ResourceMetaSearchQuery(
            created_time_start=base_time - dt.timedelta(seconds=1),
            created_time_end=end_time,
            limit=100,
        )
        results = list(self.meta_store.iter_search(q))
        # Should match item 0 and 1
        ids = sorted([r.indexed_data["id"] for r in results])
        assert ids == ["1", "2"]

        # 3. created_bys
        q = ResourceMetaSearchQuery(created_bys=["test_user"], limit=100)
        results = list(self.meta_store.iter_search(q))
        assert len(results) == len(self.sample_data)

        q = ResourceMetaSearchQuery(created_bys=["non_existent"], limit=100)
        results = list(self.meta_store.iter_search(q))
        assert len(results) == 0

        # 4. updated_time range
        q = ResourceMetaSearchQuery(
            updated_time_start=base_time - dt.timedelta(seconds=1),
            updated_time_end=end_time,
            limit=100,
        )
        results = list(self.meta_store.iter_search(q))
        ids = sorted([r.indexed_data["id"] for r in results])
        assert ids == ["1", "2"]

        # 5. updated_bys
        q = ResourceMetaSearchQuery(updated_bys=["test_user"], limit=100)
        results = list(self.meta_store.iter_search(q))
        assert len(results) == len(self.sample_data)
