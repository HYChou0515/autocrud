"""Tests for ResourceManager.list_resources method."""

import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from faker import Faker
from msgspec import UNSET, Struct

from autocrud.resource_manager.core import (
    IResourceStore,
    ResourceManager,
    SimpleStorage,
)
from autocrud.resource_manager.resource_store.simple import (
    DiskResourceStore,
    MemoryResourceStore,
)
from autocrud.types import (
    ResourceMeta,
    ResourceMetaSearchQuery,
    RevisionInfo,
    SearchedResource,
)

from .common import get_meta_store


class InnerData(Struct):
    string: str
    number: int


class Data(Struct):
    name: str
    age: int
    inner: InnerData


faker = Faker()


def new_data() -> Data:
    return Data(
        name=faker.name(),
        age=faker.pyint(min_value=0, max_value=100),
        inner=InnerData(string=faker.pystr(), number=faker.pyint()),
    )


@contextmanager
def get_resource_store(
    store_type: str, tmpdir: Path | None = None
) -> Generator[IResourceStore]:
    if store_type == "memory":
        yield MemoryResourceStore(encoding="msgpack")
    elif store_type == "disk":
        d = tmpdir / faker.pystr()
        d.mkdir()
        yield DiskResourceStore(encoding="msgpack", rootdir=d)


@pytest.fixture
def my_tmpdir():
    with tempfile.TemporaryDirectory(dir="./") as d:
        yield Path(d)


@pytest.mark.flaky(retries=3, delay=1)
@pytest.mark.parametrize("meta_store_type", ["memory", "sql3-mem"])
@pytest.mark.parametrize("res_store_type", ["memory"])
class TestListResources:
    @pytest.fixture(autouse=True)
    def setup_method(
        self,
        meta_store_type: str,
        res_store_type: str,
        my_tmpdir: Path,
    ):
        meta_store = get_meta_store(meta_store_type, tmpdir=my_tmpdir)
        with get_resource_store(res_store_type, tmpdir=my_tmpdir) as resource_store:
            storage = SimpleStorage(
                meta_store=meta_store,
                resource_store=resource_store,
            )
            self.mgr = ResourceManager(Data, storage=storage)
            yield

    def create(self, data: Data | None = None):
        data = data or new_data()
        user = faker.user_name()
        now = faker.date_time()
        with self.mgr.meta_provide(user, now):
            info = self.mgr.create(data)
        return user, now, info, data

    # ------------------------------------------------------------------
    # Basic tests
    # ------------------------------------------------------------------

    def test_list_resources_basic(self):
        """list_resources 回傳 list[SearchedResource]，三欄位都有值"""
        _, _, info1, data1 = self.create()
        _, _, info2, data2 = self.create()

        query = ResourceMetaSearchQuery()
        user, now = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user, now):
            results = self.mgr.list_resources(query)

        assert len(results) == 2
        for item in results:
            assert isinstance(item, SearchedResource)
            assert item.data is not UNSET
            assert item.info is not UNSET
            assert item.meta is not UNSET
            assert isinstance(item.info, RevisionInfo)
            assert isinstance(item.meta, ResourceMeta)

        # Verify data content matches created resources
        ids = {item.info.resource_id for item in results}
        assert info1.resource_id in ids
        assert info2.resource_id in ids

    def test_list_resources_empty(self):
        """空的搜尋結果"""
        query = ResourceMetaSearchQuery()
        user, now = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user, now):
            results = self.mgr.list_resources(query)
        assert results == []

    # ------------------------------------------------------------------
    # returns parameter tests
    # ------------------------------------------------------------------

    def test_list_resources_returns_data_only(self):
        """returns=["data"]，info/meta 為 UNSET"""
        self.create()

        query = ResourceMetaSearchQuery()
        user, now = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user, now):
            results = self.mgr.list_resources(query, returns=["data"])

        assert len(results) == 1
        item = results[0]
        assert item.data is not UNSET
        assert item.info is UNSET
        assert item.meta is UNSET

    def test_list_resources_returns_meta_only(self):
        """returns=["meta"]，data/info 為 UNSET"""
        self.create()

        query = ResourceMetaSearchQuery()
        user, now = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user, now):
            results = self.mgr.list_resources(query, returns=["meta"])

        assert len(results) == 1
        item = results[0]
        assert item.data is UNSET
        assert item.info is UNSET
        assert item.meta is not UNSET
        assert isinstance(item.meta, ResourceMeta)

    def test_list_resources_returns_info_only(self):
        """returns=["info"]，data/meta 為 UNSET"""
        self.create()

        query = ResourceMetaSearchQuery()
        user, now = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user, now):
            results = self.mgr.list_resources(query, returns=["info"])

        assert len(results) == 1
        item = results[0]
        assert item.data is UNSET
        assert item.info is not UNSET
        assert item.meta is UNSET
        assert isinstance(item.info, RevisionInfo)

    def test_list_resources_returns_data_meta(self):
        """returns=["data", "meta"]，只有 info 為 UNSET"""
        _, _, info, data = self.create()

        query = ResourceMetaSearchQuery()
        user, now = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user, now):
            results = self.mgr.list_resources(query, returns=["data", "meta"])

        assert len(results) == 1
        item = results[0]
        assert item.data is not UNSET
        assert item.info is UNSET
        assert item.meta is not UNSET
        assert item.data == data

    # ------------------------------------------------------------------
    # Partial field tests
    # ------------------------------------------------------------------

    def test_list_resources_partial_data_fields(self):
        """partial=["/name"]，data 只含 name 欄位（partial Struct）"""
        _, _, _, orig_data = self.create()

        query = ResourceMetaSearchQuery()
        user, now = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user, now):
            results = self.mgr.list_resources(
                query,
                returns=["data"],
                partial=["/name"],
            )

        assert len(results) == 1
        item = results[0]
        assert item.data is not UNSET
        # Partial struct should have name but not age
        assert hasattr(item.data, "name")
        assert item.data.name == orig_data.name
        # age should not be present (partial Struct omits it)
        assert not hasattr(item.data, "age")

    def test_list_resources_partial_with_prefix(self):
        """partial=["meta/resource_id", "data/name"]，前綴分類正確"""
        _, _, info, orig_data = self.create()

        query = ResourceMetaSearchQuery()
        user, now = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user, now):
            results = self.mgr.list_resources(
                query,
                returns=["data", "meta"],
                partial=["meta/resource_id", "data/name"],
            )

        assert len(results) == 1
        item = results[0]
        # data should be partial (only name)
        assert item.data is not UNSET
        assert hasattr(item.data, "name")
        assert item.data.name == orig_data.name
        assert not hasattr(item.data, "age")
        # meta should be partial (only resource_id)
        assert item.meta is not UNSET
        assert hasattr(item.meta, "resource_id")
        assert item.meta.resource_id == info.resource_id
        assert not hasattr(item.meta, "created_by")

    def test_list_resources_partial_info(self):
        """partial=["info/revision_id"]"""
        _, _, info, _ = self.create()

        query = ResourceMetaSearchQuery()
        user, now = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user, now):
            results = self.mgr.list_resources(
                query,
                returns=["info"],
                partial=["info/revision_id"],
            )

        assert len(results) == 1
        item = results[0]
        assert item.info is not UNSET
        assert hasattr(item.info, "revision_id")
        assert item.info.revision_id == info.revision_id
        assert not hasattr(item.info, "data_hash")

    # ------------------------------------------------------------------
    # Query filtering tests
    # ------------------------------------------------------------------

    def test_list_resources_respects_query_limit(self):
        """尊重 query 的 limit"""
        for _ in range(5):
            self.create()

        query = ResourceMetaSearchQuery(limit=3)
        user, now = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user, now):
            results = self.mgr.list_resources(query)

        assert len(results) == 3

    def test_list_resources_respects_query_offset(self):
        """尊重 query 的 offset"""
        for _ in range(5):
            self.create()

        query = ResourceMetaSearchQuery(offset=2)
        user, now = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user, now):
            results = self.mgr.list_resources(query)

        assert len(results) == 3  # 5 total, offset=2, default limit=10

    def test_list_resources_respects_is_deleted(self):
        """is_deleted 過濾正確"""
        _, _, info1, _ = self.create()
        _, _, info2, _ = self.create()

        # 刪除第一個
        user, now = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user, now):
            self.mgr.delete(info1.resource_id)

        # 搜尋未刪除的
        query = ResourceMetaSearchQuery(is_deleted=False)
        with self.mgr.meta_provide(user, now):
            results = self.mgr.list_resources(query)

        assert len(results) == 1
        assert results[0].meta.resource_id == info2.resource_id

    # ------------------------------------------------------------------
    # Parallel execution test
    # ------------------------------------------------------------------

    def test_list_resources_parallel_execution(self):
        """>10 個資源時走並行路徑"""
        created = []
        for _ in range(15):
            _, _, info, data = self.create()
            created.append((info, data))

        query = ResourceMetaSearchQuery(limit=15)
        user, now = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user, now):
            results = self.mgr.list_resources(query)

        assert len(results) == 15
        result_ids = {item.info.resource_id for item in results}
        for info, _ in created:
            assert info.resource_id in result_ids

    # ------------------------------------------------------------------
    # Error handling test
    # ------------------------------------------------------------------

    def test_list_resources_error_skip(self):
        """單個資源 fetch 失敗會被跳過"""
        _, _, info1, _ = self.create()
        _, _, info2, _ = self.create()

        # Monkey-patch get to fail for the first resource
        original_get = self.mgr.get

        def failing_get(resource_id, **kwargs):
            if resource_id == info1.resource_id:
                raise RuntimeError("Simulated failure")
            return original_get(resource_id, **kwargs)

        self.mgr.get = failing_get

        query = ResourceMetaSearchQuery()
        user, now = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user, now):
            results = self.mgr.list_resources(query)

        # 只有成功取得的資源
        assert len(results) == 1
        assert results[0].info.resource_id == info2.resource_id

    # ------------------------------------------------------------------
    # Data correctness test
    # ------------------------------------------------------------------

    def test_list_resources_data_matches_get(self):
        """list_resources 的 data 應與直接 get 的結果一致"""
        _, _, info, orig_data = self.create()

        query = ResourceMetaSearchQuery()
        user, now = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user, now):
            results = self.mgr.list_resources(query)
            direct = self.mgr.get(info.resource_id)

        assert len(results) == 1
        assert results[0].data == direct.data
        assert results[0].info == direct.info

    # ------------------------------------------------------------------
    # search_resources delegation test
    # ------------------------------------------------------------------

    def test_list_resources_delegates_to_search_resources(self):
        """list_resources 內部呼叫 search_resources"""
        _, _, info, _ = self.create()

        query = ResourceMetaSearchQuery()
        user, now = faker.user_name(), faker.date_time()

        # Verify search_resources is called by monkeypatching
        original = self.mgr.search_resources
        call_args = []

        def spy(q):
            call_args.append(q)
            return original(q)

        self.mgr.search_resources = spy
        with self.mgr.meta_provide(user, now):
            results = self.mgr.list_resources(query)

        assert len(call_args) == 1
        assert call_args[0] is query
        assert len(results) == 1

    # ------------------------------------------------------------------
    # QB query support test
    # ------------------------------------------------------------------

    def test_list_resources_accepts_query_builder(self):
        """list_resources 也接受 Query builder 物件（使用 meta field）"""
        from autocrud.query import QB

        _, _, info, data = self.create()

        q = QB.resource_id() == info.resource_id
        user, now = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user, now):
            results = self.mgr.list_resources(q)

        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0].meta.resource_id == info.resource_id
