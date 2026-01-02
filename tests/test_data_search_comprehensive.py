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

    def _assert_search_results(self, conditions):
        """Run search and verify results against in-memory filtering."""
        query = ResourceMetaSearchQuery(
            data_conditions=conditions,
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

        assert result_ids, "Result set is empty"
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
