import datetime as dt
import time
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path
from uuid import uuid4

import jsonpatch
import msgspec
import psycopg2
import pytest
import redis
from faker import Faker
from msgspec import UNSET, Struct, UnsetType

from autocrud.types import (
    CannotModifyResourceError,
    ResourceIDNotFoundError,
    ResourceIsDeletedError,
    ResourceMetaSortKey,
    RevisionInfo,
    RevisionStatus,
)
from autocrud.resource_manager.core import (
    IResourceStore,
    ResourceManager,
    SimpleStorage,
)
from autocrud.resource_manager.meta_store.df import DFMemoryMetaStore
from autocrud.resource_manager.meta_store.fast_slow import FastSlowMetaStore
from autocrud.resource_manager.meta_store.postgres import PostgresMetaStore
from autocrud.resource_manager.meta_store.redis import RedisMetaStore
from autocrud.resource_manager.meta_store.simple import (
    DiskMetaStore,
    MemoryMetaStore,
)
from autocrud.resource_manager.meta_store.sqlite3 import (
    FileSqliteMetaStore,
    MemorySqliteMetaStore,
)
from autocrud.resource_manager.resource_store.simple import (
    DiskResourceStore,
    MemoryResourceStore,
)
from autocrud.types import (
    ResourceMeta,
    ResourceMetaSearchQuery,
    ResourceMetaSearchSort,
    ResourceMetaSortDirection,
)


class InnerData(Struct):
    string: str
    number: int
    fp: float
    times: dt.datetime


class Data(Struct):
    string: str
    number: int
    fp: float
    times: dt.datetime
    data: InnerData
    list_data: list[InnerData]
    dict_data: dict[str, InnerData]


faker = Faker()


def new_inner_data() -> InnerData:
    return InnerData(
        string=faker.pystr(),
        number=faker.pyint(),
        fp=faker.pyfloat(),
        times=faker.date_time(),
    )


def new_data() -> Data:
    return Data(
        string=faker.pystr(),
        number=faker.pyint(),
        fp=faker.pyfloat(),
        times=faker.date_time(),
        data=new_inner_data(),
        list_data=[new_inner_data() for _ in faker.pylist(variable_nb_elements=True)],
        dict_data={
            faker.pystr(): new_inner_data()
            for _ in faker.pylist(variable_nb_elements=True)
        },
    )


def reset_and_get_pg_dsn():
    pg_dsn = "postgresql://postgres:mysecretpassword@localhost:5432/your_database"
    pg_conn = psycopg2.connect(pg_dsn)
    with pg_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS resource_meta;")
        pg_conn.commit()
    pg_conn.close()
    return pg_dsn


def reset_and_get_redis_url():
    redis_url = "redis://localhost:6379/0"
    client = redis.Redis.from_url(redis_url)
    client.flushall()
    client.close()
    return redis_url


def get_meta_store(store_type: str, tmpdir: Path = None):
    """Fixture to provide a fast store for testing."""
    if store_type == "memory":
        return MemoryMetaStore(encoding="msgpack")
    if store_type == "dfm":
        return DFMemoryMetaStore(encoding="msgpack")
    if store_type == "sql3-mem":
        return MemorySqliteMetaStore(encoding="msgpack")
    if store_type == "memory-pg":
        return FastSlowMetaStore(
            fast_store=MemoryMetaStore(encoding="msgpack"),
            slow_store=PostgresMetaStore(
                pg_dsn=reset_and_get_pg_dsn(),
                encoding="msgpack",
            ),
        )
    if store_type == "sql3-file":
        return FileSqliteMetaStore(db_filepath=tmpdir / "meta.db", encoding="msgpack")
    if store_type == "disk-sql3file":
        d = tmpdir / faker.pystr()
        d.mkdir()
        return FastSlowMetaStore(
            fast_store=DiskMetaStore(encoding="msgpack", rootdir=d),
            slow_store=FileSqliteMetaStore(
                db_filepath=d / "meta.db",
                encoding="msgpack",
            ),
        )
    if store_type == "redis":
        return RedisMetaStore(
            redis_url=reset_and_get_redis_url(),
            encoding="msgpack",
            prefix=str(tmpdir).rsplit("/", 1)[-1],
        )
    if store_type == "redis-pg":
        return FastSlowMetaStore(
            fast_store=RedisMetaStore(
                redis_url=reset_and_get_redis_url(),
                encoding="msgpack",
                prefix=str(tmpdir).rsplit("/", 1)[-1],
            ),
            slow_store=PostgresMetaStore(
                pg_dsn=reset_and_get_pg_dsn(),
                encoding="msgpack",
            ),
        )
    d = tmpdir / faker.pystr()
    d.mkdir()
    return DiskMetaStore(encoding="msgpack", rootdir=d)


@contextmanager
def get_resource_store(
    store_type: str, tmpdir: Path | None = None
) -> Generator[IResourceStore]:
    """Fixture to provide a fast store for testing."""
    if store_type == "memory":
        yield MemoryResourceStore(encoding="msgpack")
    elif store_type == "disk":
        d = tmpdir / faker.pystr()
        d.mkdir()
        yield DiskResourceStore(encoding="msgpack", rootdir=d)
    elif store_type == "s3":
        from autocrud.resource_manager.resource_store.s3 import S3ResourceStore

        s3 = S3ResourceStore(
            encoding="msgpack",
            endpoint_url="http://localhost:9000",
            prefix=str(tmpdir).rsplit("/", 1)[-1] + "/",
        )
        with suppress(Exception):
            yield s3
        try:
            s3.cleanup()
        except Exception as e:
            print(f"Error cleaning up S3 store: {e}")


@pytest.mark.flaky(retries=6, delay=1)
@pytest.mark.parametrize(
    "meta_store_type",
    ["memory", "sql3-mem", "sql3-file", "redis", "disk", "redis-pg"],
)
@pytest.mark.parametrize("res_store_type", ["memory", "disk", "s3"])
class TestResourceManager:
    @pytest.fixture(autouse=True)
    def setup_method(
        self,
        meta_store_type: str,
        res_store_type: str,
        my_tmpdir: str,
    ):
        meta_store = get_meta_store(meta_store_type, tmpdir=my_tmpdir)
        with get_resource_store(res_store_type, tmpdir=my_tmpdir) as resource_store:
            storage = SimpleStorage(
                meta_store=meta_store,
                resource_store=resource_store,
            )
            self.mgr = ResourceManager(Data, storage=storage)
            yield

    def create(self, data: Data, *, status: RevisionStatus | UnsetType = UNSET):
        user = faker.user_name()
        now = faker.date_time()
        with self.mgr.meta_provide(user, now):
            meta = self.mgr.create(data, status=status)
        return user, now, meta

    def assert_valid_datahash(self, data_hash: str):
        assert data_hash.startswith("xxh3_128:")
        assert len(data_hash) == 41

    def test_create(self):
        data = new_data()
        user, now, meta = self.create(data)
        got = self.mgr.get(meta.resource_id)
        assert got.data == data
        assert got.data is not data
        assert got.info == meta
        assert got.info.created_by == user
        assert got.info.updated_by == user
        assert got.info.created_time == now
        assert got.info.updated_time == now
        assert got.info.status == "stable"
        assert got.info.parent_revision_id is None
        assert got.info.schema_version is None
        self.assert_valid_datahash(got.info.data_hash)
        assert got.info.uid
        assert got.info.resource_id
        res_meta = self.mgr._get_meta_no_check_is_deleted(meta.resource_id)
        assert res_meta.current_revision_id == got.info.revision_id
        assert res_meta.resource_id == got.info.resource_id
        assert res_meta.total_revision_count == 1
        assert res_meta.created_time == now
        assert res_meta.created_by == user
        assert res_meta.updated_time == now
        assert res_meta.updated_by == user
        assert res_meta.schema_version is None

    def test_create_invalid_data(self):
        invalid_data = Data(
            string=123,  # 應為 str
            number="not_a_number",  # 應為 int
            fp="not_a_float",  # 應為 float
            times="not_a_datetime",  # 應為 datetime
            data="not_an_inner_data",  # 應為 InnerData
            list_data="not_a_list",  # 應為 list[InnerData]
            dict_data="not_a_dict",  # 應為 dict[str, InnerData]
        )
        user = faker.user_name()
        now = faker.date_time()
        with self.mgr.meta_provide(user, now), pytest.raises(msgspec.ValidationError):
            self.mgr.create(invalid_data)

    def test_modify_stable_raises(self):
        data = new_data()
        user, now, meta = self.create(data)
        assert meta.status == "stable"
        u_data = new_data()
        u_user = faker.user_name()
        u_now = faker.date_time()
        with (
            pytest.raises(CannotModifyResourceError),
            self.mgr.meta_provide(u_user, u_now),
        ):
            self.mgr.modify(meta.resource_id, u_data)
        got = self.mgr.get(meta.resource_id)
        assert got.info == meta
        assert got.data == data
        res_meta = self.mgr._get_meta_no_check_is_deleted(meta.resource_id)
        assert res_meta.current_revision_id == meta.revision_id
        assert res_meta.resource_id == meta.resource_id
        assert res_meta.total_revision_count == 1
        assert res_meta.created_time == now
        assert res_meta.created_by == user
        assert res_meta.updated_time == now
        assert res_meta.updated_by == user

    def check_modified_info(
        self,
        before: tuple[RevisionInfo, str, dt.datetime],
        after: tuple[RevisionInfo, str, dt.datetime, Data, str],
    ):
        info, user, now = before
        u_info, u_user, u_now, u_data, u_status = after
        assert u_info.uid != info.uid
        assert u_info.resource_id == info.resource_id
        assert u_info.revision_id == info.revision_id
        assert u_info.parent_revision_id == info.parent_revision_id
        assert u_info.schema_version is None
        self.assert_valid_datahash(u_info.data_hash)
        assert u_info.status == u_status
        assert u_info.created_time == now
        assert u_info.updated_time == u_now
        assert u_info.created_by == user
        assert u_info.updated_by == u_user
        got = self.mgr.get(info.resource_id)
        assert got.info == u_info
        assert got.data == u_data
        res_meta = self.mgr._get_meta_no_check_is_deleted(info.resource_id)
        assert res_meta.current_revision_id == u_info.revision_id
        assert res_meta.resource_id == u_info.resource_id
        assert res_meta.total_revision_count == 1
        assert res_meta.created_time == now
        assert res_meta.created_by == user
        assert res_meta.updated_time == u_now
        assert res_meta.updated_by == u_user

    def test_modify(self):
        data = new_data()
        user, now, meta = self.create(data, status=RevisionStatus.draft)
        assert meta.status == "draft"
        u_data = new_data()
        u_user = faker.user_name()
        u_now = faker.date_time()
        with self.mgr.meta_provide(u_user, u_now):
            u_meta = self.mgr.modify(meta.resource_id, u_data)
        self.check_modified_info(
            (meta, user, now), (u_meta, u_user, u_now, u_data, "draft")
        )

        u2_user = faker.user_name()
        u2_now = faker.date_time()
        with self.mgr.meta_provide(u2_user, u2_now):
            u2_meta = self.mgr.modify(meta.resource_id, status=RevisionStatus.stable)
        self.check_modified_info(
            (meta, user, now), (u2_meta, u2_user, u2_now, u_data, "stable")
        )

        with (
            pytest.raises(CannotModifyResourceError),
            self.mgr.meta_provide(u_user, u_now),
        ):
            self.mgr.modify(meta.resource_id, u_data)

        u3_user = faker.user_name()
        u3_now = faker.date_time()
        u3_data = new_data()
        with self.mgr.meta_provide(u3_user, u3_now):
            u3_meta = self.mgr.modify(
                meta.resource_id, u3_data, status=RevisionStatus.draft
            )
        self.check_modified_info(
            (meta, user, now), (u3_meta, u3_user, u3_now, u3_data, "draft")
        )

        # modify with patch
        p_user = faker.user_name()
        p_now = faker.date_time()
        p_data = new_data()
        p_patch = jsonpatch.make_patch(
            msgspec.to_builtins(u3_data), msgspec.to_builtins(p_data)
        )
        with self.mgr.meta_provide(p_user, p_now):
            u3_meta = self.mgr.modify(
                meta.resource_id, p_patch, status=RevisionStatus.draft
            )
        self.check_modified_info(
            (meta, user, now), (u3_meta, p_user, p_now, p_data, "draft")
        )

        # modify status to stable
        u4_user = faker.user_name()
        u4_now = faker.date_time()
        u4_data = new_data()
        with (
            self.mgr.meta_provide(u4_user, u4_now),
        ):
            u4_meta = self.mgr.modify(
                meta.resource_id, u4_data, status=RevisionStatus.stable
            )
        self.check_modified_info(
            (meta, user, now), (u4_meta, u4_user, u4_now, u4_data, "stable")
        )

    def test_update(self):
        data = new_data()
        user, now, meta = self.create(data)
        u_data = new_data()
        u_user = faker.user_name()
        u_now = faker.date_time()
        with self.mgr.meta_provide(u_user, u_now):
            u_meta = self.mgr.update(meta.resource_id, u_data)
        assert u_meta.uid != meta.uid
        assert u_meta.resource_id == meta.resource_id
        assert u_meta.revision_id != meta.revision_id
        assert u_meta.parent_revision_id == meta.revision_id
        assert u_meta.schema_version is None
        self.assert_valid_datahash(u_meta.data_hash)
        assert u_meta.status == "stable"
        assert u_meta.created_time == u_now
        assert u_meta.updated_time == u_now
        assert u_meta.created_by == u_user
        assert u_meta.updated_by == u_user
        got = self.mgr.get(meta.resource_id)
        assert got.info == u_meta
        assert got.data == u_data
        res_meta = self.mgr._get_meta_no_check_is_deleted(meta.resource_id)
        assert res_meta.current_revision_id == u_meta.revision_id
        assert res_meta.resource_id == u_meta.resource_id
        assert res_meta.total_revision_count == 2
        assert res_meta.created_time == now
        assert res_meta.created_by == user
        assert res_meta.updated_time == u_now
        assert res_meta.updated_by == u_user

    def test_patch_invalid(self):
        data = new_data()
        user, now, meta = self.create(data)

        # 使用 RFC 6902 JSON Patch 格式進行部分更新
        patch_operations = [
            {"op": "replace", "path": "/string", "value": faker.pyint()},
        ]

        # 創建 JsonPatch 對象
        patch = jsonpatch.JsonPatch(patch_operations)

        with pytest.raises(msgspec.ValidationError):
            self.mgr.patch(meta.resource_id, patch)

    def test_patch(self):
        data = new_data()
        user, now, meta = self.create(data)

        # 使用 RFC 6902 JSON Patch 格式進行部分更新
        new_string = faker.pystr()
        new_number = faker.pyint()
        new_inner = new_inner_data()

        # 將 msgspec.Struct 轉換為字典格式供 jsonpatch 使用
        new_inner_dict = {
            "string": new_inner.string,
            "number": new_inner.number,
            "fp": new_inner.fp,
            "times": new_inner.times.isoformat(),  # 將 datetime 轉換為 ISO 格式字串
        }

        patch_operations = [
            {"op": "replace", "path": "/string", "value": new_string},
            {"op": "replace", "path": "/number", "value": new_number},
            {"op": "replace", "path": "/data/string", "value": "updated_inner_string"},
            {"op": "add", "path": "/list_data/-", "value": new_inner_dict},
            {"op": "remove", "path": "/dict_data/" + list(data.dict_data.keys())[0]},
        ]

        # 創建 JsonPatch 對象
        patch = jsonpatch.JsonPatch(patch_operations)

        p_user = faker.user_name()
        p_now = faker.date_time()

        with self.mgr.meta_provide(p_user, p_now):
            p_meta = self.mgr.patch(meta.resource_id, patch)

        # 驗證 patch 後的 metadata
        assert p_meta.uid != meta.uid
        assert p_meta.resource_id == meta.resource_id
        assert p_meta.revision_id != meta.revision_id
        assert p_meta.parent_revision_id == meta.revision_id
        assert p_meta.schema_version is None
        self.assert_valid_datahash(p_meta.data_hash)
        assert p_meta.status == "stable"
        assert p_meta.created_time == p_now
        assert p_meta.updated_time == p_now
        assert p_meta.created_by == p_user
        assert p_meta.updated_by == p_user

        # 驗證 patch 後的資料：根據 JSON Patch 操作驗證結果
        got = self.mgr.get(meta.resource_id)
        assert got.info == p_meta
        assert got.data.string == new_string  # replace 操作已更新
        assert got.data.number == new_number  # replace 操作已更新
        assert got.data.fp == data.fp  # 未被 patch 操作影響，保持原值
        assert got.data.times == data.times  # 未被 patch 操作影響，保持原值
        assert (
            got.data.data.string == "updated_inner_string"
        )  # replace 操作已更新巢狀資料
        assert got.data.data.number == data.data.number  # 巢狀資料的其他欄位保持原值
        assert got.data.data.fp == data.data.fp  # 巢狀資料的其他欄位保持原值
        assert got.data.data.times == data.data.times  # 巢狀資料的其他欄位保持原值
        assert (
            len(got.data.list_data) == len(data.list_data) + 1
        )  # add 操作增加了一個元素
        # 驗證新增的元素（最後一個）的內容
        added_item = got.data.list_data[-1]
        assert added_item.string == new_inner.string
        assert added_item.number == new_inner.number
        assert added_item.fp == new_inner.fp
        assert added_item.times == new_inner.times
        # dict_data 應該少了一個 key (remove 操作)
        if data.dict_data:
            assert len(got.data.dict_data) == len(data.dict_data) - 1

        # 驗證 resource metadata
        res_meta = self.mgr._get_meta_no_check_is_deleted(meta.resource_id)
        assert res_meta.current_revision_id == p_meta.revision_id
        assert res_meta.resource_id == p_meta.resource_id
        assert res_meta.total_revision_count == 2
        assert res_meta.created_time == now
        assert res_meta.created_by == user
        assert res_meta.updated_time == p_now
        assert res_meta.updated_by == p_user

    def test_switch(self):
        # 創建初始版本
        data1 = new_data()
        user1, now1, meta1 = self.create(data1)

        # 第一次更新
        data2 = new_data()
        user2, now2 = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user2, now2):
            meta2 = self.mgr.update(meta1.resource_id, data2)

        # 第二次更新
        data3 = new_data()
        user3, now3 = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user3, now3):
            meta3 = self.mgr.update(meta1.resource_id, data3)

        # Switch 到 revision 1
        switch_user = faker.user_name()
        switch_now = faker.date_time()
        with self.mgr.meta_provide(switch_user, switch_now):
            switch_result = self.mgr.switch(meta1.resource_id, meta1.revision_id)

        # 驗證 switch 後的 ResourceMeta
        assert isinstance(switch_result, ResourceMeta)
        assert (
            switch_result.current_revision_id == meta1.revision_id
        )  # 改變為 revision 1
        assert switch_result.resource_id == meta1.resource_id
        assert switch_result.total_revision_count == 3  # 總數不變
        assert switch_result.created_time == now1  # 創建時間不變
        assert switch_result.created_by == user1  # 創建者不變
        assert switch_result.updated_time == switch_now  # 更新時間是 switch 的時間
        assert switch_result.updated_by == switch_user  # 更新者是 switch 的用戶

        # 驗證 get_meta 返回的結果與 switch 結果一致
        res_meta_after = self.mgr._get_meta_no_check_is_deleted(meta1.resource_id)
        assert res_meta_after == switch_result

        # 驗證 get 返回的資料現在是 data1
        current_after = self.mgr.get(meta1.resource_id)
        assert current_after.data == data1
        assert current_after.info.revision_id == meta1.revision_id

        # 重點測試：從當前 revision (meta1) 進行 update
        data4 = new_data()
        user4, now4 = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user4, now4):
            meta4 = self.mgr.update(meta1.resource_id, data4)

        # 驗證新的 revision 4 的 parent_revision_id 是當前的 current_revision_id (meta1)
        assert meta4.parent_revision_id == meta1.revision_id
        assert meta4.resource_id == meta1.resource_id
        assert meta4.revision_id != meta1.revision_id
        assert meta4.revision_id != meta2.revision_id
        assert meta4.revision_id != meta3.revision_id

        # 驗證 ResourceMeta 的 current_revision_id 更新為 meta4
        res_meta_final = self.mgr._get_meta_no_check_is_deleted(meta1.resource_id)
        assert res_meta_final.current_revision_id == meta4.revision_id
        assert res_meta_final.total_revision_count == 4

        # 驗證當前資料是 data4
        current_final = self.mgr.get(meta1.resource_id)
        assert current_final.data == data4
        assert current_final.info.revision_id == meta4.revision_id

        # 再次 switch 到 revision 2，然後測試 patch
        with self.mgr.meta_provide(switch_user, switch_now):
            self.mgr.switch(meta1.resource_id, meta2.revision_id)

        # 從 revision 2 進行 patch
        patch_operations = [
            {"op": "replace", "path": "/string", "value": "patched_from_rev2"},
        ]
        patch = jsonpatch.JsonPatch(patch_operations)

        user5, now5 = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user5, now5):
            meta5 = self.mgr.patch(meta1.resource_id, patch)

        # 驗證 patch 產生的新 revision 5 的 parent_revision_id 是 meta2
        assert meta5.parent_revision_id == meta2.revision_id

    def test_switch_to_same_revision(self):
        """測試 switch 到相同的 revision_id 時不做任何事"""
        # 創建初始版本
        data1 = new_data()
        user1, now1, meta1 = self.create(data1)

        # 創建第二個版本
        data2 = new_data()
        user2, now2 = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user2, now2):
            meta2 = self.mgr.update(meta1.resource_id, data2)

        # 獲取 switch 前的 ResourceMeta
        res_meta_before = self.mgr._get_meta_no_check_is_deleted(meta1.resource_id)
        assert res_meta_before.current_revision_id == meta2.revision_id
        assert res_meta_before.updated_time == now2
        assert res_meta_before.updated_by == user2

        # Switch 到當前已經是的 revision (meta2) - 應該不做任何事
        switch_user = faker.user_name()
        switch_now = faker.date_time()
        with self.mgr.meta_provide(switch_user, switch_now):
            switch_result = self.mgr.switch(meta1.resource_id, meta2.revision_id)

        # 驗證 switch 後的 ResourceMeta 完全沒有改變
        assert switch_result == res_meta_before  # 完全相同
        assert (
            switch_result.current_revision_id == meta2.revision_id
        )  # current_revision_id 沒變
        assert switch_result.updated_time == now2  # updated_time 沒變（重點！）
        assert switch_result.updated_by == user2  # updated_by 沒變（重點！）

        # 再次驗證 get_meta 返回的結果也沒有改變
        res_meta_after = self.mgr._get_meta_no_check_is_deleted(meta1.resource_id)
        assert res_meta_after == res_meta_before
        assert res_meta_after.updated_time == now2  # 時間戳沒有更新
        assert res_meta_after.updated_by == user2  # 用戶沒有更新

    def test_delete(self):
        """測試軟刪除功能"""
        # 創建初始版本
        data1 = new_data()
        user1, now1, meta1 = self.create(data1)

        # 創建第二個版本
        data2 = new_data()
        user2, now2 = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user2, now2):
            meta2 = self.mgr.update(meta1.resource_id, data2)

        # 驗證刪除前的狀態
        res_meta_before = self.mgr._get_meta_no_check_is_deleted(meta1.resource_id)
        assert res_meta_before.is_deleted is False
        assert res_meta_before.current_revision_id == meta2.revision_id
        assert res_meta_before.updated_time == now2
        assert res_meta_before.updated_by == user2

        # 執行軟刪除
        delete_user = faker.user_name()
        delete_now = faker.date_time()
        with self.mgr.meta_provide(delete_user, delete_now):
            delete_result = self.mgr.delete(meta1.resource_id)

        # 驗證 delete 方法返回的 ResourceMeta
        assert isinstance(delete_result, ResourceMeta)
        assert delete_result.is_deleted is True  # 標記為已刪除
        assert (
            delete_result.current_revision_id == meta2.revision_id
        )  # current_revision_id 不變
        assert delete_result.resource_id == meta1.resource_id  # resource_id 不變
        assert delete_result.total_revision_count == 2  # 總數不變
        assert delete_result.created_time == now1  # 創建時間不變
        assert delete_result.created_by == user1  # 創建者不變
        assert delete_result.updated_time == delete_now  # 更新時間是刪除的時間
        assert delete_result.updated_by == delete_user  # 更新者是刪除的用戶

        # 重點1: 刪除後，任何 get_meta 會回傳 is_deleted=True
        assert (
            self.mgr._get_meta_no_check_is_deleted(meta1.resource_id) == delete_result
        )

        # 重點4: 刪除後的 updated_time/updated_by
        assert delete_result.updated_time == delete_now  # 更新時間是刪除的時間
        assert delete_result.updated_by == delete_user  # 更新者是刪除的用戶

        # 驗證所有 revision 資料仍然存在（軟刪除不刪除實際資料）
        assert self.mgr.storage.exists(meta1.resource_id)
        assert self.mgr.storage.revision_exists(meta1.resource_id, meta1.revision_id)
        assert self.mgr.storage.revision_exists(meta1.resource_id, meta2.revision_id)

        # 重點2: 刪除後，CRUD 會 raise ResourceIsDeletedError
        with pytest.raises(ResourceIsDeletedError):
            self.mgr.get(meta1.resource_id)

        with pytest.raises(ResourceIsDeletedError):
            self.mgr.update(meta1.resource_id, new_data())

        with pytest.raises(ResourceIsDeletedError):
            patch = jsonpatch.JsonPatch(
                [{"op": "replace", "path": "/string", "value": "test"}],
            )
            self.mgr.patch(meta1.resource_id, patch)

        with pytest.raises(ResourceIsDeletedError):
            self.mgr.switch(meta1.resource_id, meta1.revision_id)

    def test_delete_already_deleted(self):
        """重點3: 刪除已刪除的東西是不可以的"""
        # 創建資源
        data = new_data()
        user, now, meta = self.create(data)

        # 第一次刪除
        delete_user1 = faker.user_name()
        delete_now1 = faker.date_time()
        with self.mgr.meta_provide(delete_user1, delete_now1):
            self.mgr.delete(meta.resource_id)

        # 嘗試再次刪除已刪除的資源 - 應該 raise ResourceIsDeletedError
        delete_user2 = faker.user_name()
        delete_now2 = faker.date_time()
        with pytest.raises(ResourceIsDeletedError):
            with self.mgr.meta_provide(delete_user2, delete_now2):
                self.mgr.delete(meta.resource_id)

    def test_delete_nonexistent_resource(self):
        """重點3: 刪除不存在的東西是不可以的"""
        nonexistent_id = "nonexistent-resource-id"

        delete_user = faker.user_name()
        delete_now = faker.date_time()

        with pytest.raises(ResourceIDNotFoundError):
            with self.mgr.meta_provide(delete_user, delete_now):
                self.mgr.delete(nonexistent_id)

    def test_restore(self):
        """測試還原功能"""
        # 創建初始版本
        data1 = new_data()
        user1, now1, meta1 = self.create(data1)

        # 創建第二個版本
        data2 = new_data()
        user2, now2 = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user2, now2):
            meta2 = self.mgr.update(meta1.resource_id, data2)

        # 執行軟刪除
        delete_user = faker.user_name()
        delete_now = faker.date_time()
        with self.mgr.meta_provide(delete_user, delete_now):
            self.mgr.delete(meta1.resource_id)

        # 驗證已刪除
        res_meta_deleted = self.mgr._get_meta_no_check_is_deleted(meta1.resource_id)
        assert res_meta_deleted.is_deleted is True

        # 執行還原
        restore_user = faker.user_name()
        restore_now = faker.date_time()
        with self.mgr.meta_provide(restore_user, restore_now):
            restore_result = self.mgr.restore(meta1.resource_id)

        # 驗證 restore 方法返回的 ResourceMeta
        assert isinstance(restore_result, ResourceMeta)
        assert restore_result.is_deleted is False  # 不再標記為已刪除
        assert (
            restore_result.current_revision_id == meta2.revision_id
        )  # current_revision_id 不變
        assert restore_result.resource_id == meta1.resource_id  # resource_id 不變
        assert restore_result.total_revision_count == 2  # 總數不變
        assert restore_result.created_time == now1  # 創建時間不變
        assert restore_result.created_by == user1  # 創建者不變
        assert restore_result.updated_time == restore_now  # 更新時間是還原的時間
        assert restore_result.updated_by == restore_user  # 更新者是還原的用戶

        # 驗證 restore 返回的 meta 與 get_meta 返回的一致
        assert restore_result == self.mgr._get_meta_no_check_is_deleted(
            meta1.resource_id,
        )

        # 驗證 CRUD 操作重新可用
        current_data = self.mgr.get(meta1.resource_id)
        assert current_data.data == data2
        assert current_data.info.revision_id == meta2.revision_id

        # 驗證可以進行更新
        data3 = new_data()
        user3, now3 = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user3, now3):
            meta3 = self.mgr.update(meta1.resource_id, data3)

        assert meta3.parent_revision_id == meta2.revision_id

    def test_restore_nonexistent_resource(self):
        """重點6: restore 不存在的東西是不可以的"""
        nonexistent_id = "nonexistent-resource-id"

        restore_user = faker.user_name()
        restore_now = faker.date_time()

        with pytest.raises(ResourceIDNotFoundError):
            with self.mgr.meta_provide(restore_user, restore_now):
                self.mgr.restore(nonexistent_id)

    def test_restore_non_deleted_resource(self):
        """測試還原未刪除的資源（邊界情況）"""
        # 創建資源但不刪除
        data = new_data()
        user, now, meta = self.create(data)

        # 獲取還原前的狀態
        res_meta_before = self.mgr._get_meta_no_check_is_deleted(meta.resource_id)
        assert res_meta_before.is_deleted is False

        # 執行還原（即使未刪除）
        restore_user = faker.user_name()
        restore_now = faker.date_time()
        with self.mgr.meta_provide(restore_user, restore_now):
            restore_result = self.mgr.restore(meta.resource_id)

        # 驗證 restore 方法返回的 ResourceMeta（未刪除資源的情況）
        assert isinstance(restore_result, ResourceMeta)
        assert restore_result.is_deleted is False  # 仍然是 False
        assert restore_result.updated_time == now  # 時間戳不會更新
        assert restore_result.updated_by == user  # 用戶不會更新

        # 驗證 restore 返回的 meta 與 get_meta 返回的一致
        assert restore_result == self.mgr._get_meta_no_check_is_deleted(
            meta.resource_id,
        )

    def test_search_resources_basic(self):
        """測試基本的資源搜索功能"""
        # 創建多個資源用於測試
        data1 = new_data()
        user1, now1, meta1 = self.create(data1)

        data2 = new_data()
        user2, now2, meta2 = self.create(data2)

        # 基本搜索 - 默認參數
        query = ResourceMetaSearchQuery()
        with self.mgr.meta_provide(user1, now1):
            results = self.mgr.search_resources(query)
        results_id = [meta.resource_id for meta in results]

        # 應該返回兩個結果（因為 limit=10，只有2個資源）
        assert len(results_id) == 2
        # 結果應該包含兩個資源的 ID
        assert meta1.resource_id in results_id
        assert meta2.resource_id in results_id

    def test_search_resources_with_limit_and_offset(self):
        """測試分頁功能"""
        # 創建多個資源
        resources = []
        for i in range(5):
            data = new_data()
            user, now, meta = self.create(data)
            resources.append((user, now, meta))

        # 測試 limit
        query = ResourceMetaSearchQuery(limit=3)
        user, now = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user, now):
            results = self.mgr.search_resources(query)
        assert len(results) == 3

        # 測試 offset
        query = ResourceMetaSearchQuery(offset=2)
        with self.mgr.meta_provide(user, now):
            results_with_offset = self.mgr.search_resources(query)
        assert len(results_with_offset) == 3  # 總共5個，offset=2，limit=10，應該有3個

    def test_search_resources_by_deletion_status(self):
        """測試按刪除狀態搜索"""
        # 創建資源
        data1 = new_data()
        user1, now1, meta1 = self.create(data1)

        data2 = new_data()
        user2, now2, meta2 = self.create(data2)

        # 刪除一個資源
        delete_user, delete_now = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(delete_user, delete_now):
            self.mgr.delete(meta1.resource_id)

        # 搜索未刪除的資源
        query = ResourceMetaSearchQuery(is_deleted=False)
        user, now = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(user, now):
            results = self.mgr.search_resources(query)
        results_id = [meta.resource_id for meta in results]
        assert meta2.resource_id in results_id
        assert meta1.resource_id not in results_id

        # 搜索已刪除的資源
        query = ResourceMetaSearchQuery(is_deleted=True)
        with self.mgr.meta_provide(user, now):
            results = self.mgr.search_resources(query)
        results_id = [meta.resource_id for meta in results]
        assert meta1.resource_id in results_id
        assert meta2.resource_id not in results_id

    def test_search_resources_by_user(self):
        """測試按用戶搜索"""
        # 使用不同用戶創建資源
        data1 = new_data()
        user1 = "test_user_1"
        now1 = faker.date_time()
        with self.mgr.meta_provide(user1, now1):
            meta1 = self.mgr.create(data1)

        data2 = new_data()
        user2 = "test_user_2"
        now2 = faker.date_time()
        with self.mgr.meta_provide(user2, now2):
            meta2 = self.mgr.create(data2)

        # 按創建者搜索
        query = ResourceMetaSearchQuery(created_bys=[user1])
        search_user, search_now = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(search_user, search_now):
            results = self.mgr.search_resources(query)
        results_id = [meta.resource_id for meta in results]
        assert meta1.resource_id in results_id
        assert meta2.resource_id not in results_id

        # 按多個創建者搜索
        query = ResourceMetaSearchQuery(created_bys=[user1, user2])
        with self.mgr.meta_provide(search_user, search_now):
            results = self.mgr.search_resources(query)
        results_id = [meta.resource_id for meta in results]
        assert meta1.resource_id in results_id
        assert meta2.resource_id in results_id

    def test_search_resources_by_time_range(self):
        """測試按時間範圍搜索"""
        # 創建資源在不同時間點
        base_time = dt.datetime(2023, 1, 1, 12, 0, 0)

        data1 = new_data()
        user1, meta1 = faker.user_name(), None
        with self.mgr.meta_provide(user1, base_time):
            meta1 = self.mgr.create(data1)

        data2 = new_data()
        user2, meta2 = faker.user_name(), None
        with self.mgr.meta_provide(user2, base_time + dt.timedelta(hours=1)):
            meta2 = self.mgr.create(data2)

        data3 = new_data()
        user3, meta3 = faker.user_name(), None
        with self.mgr.meta_provide(user3, base_time + dt.timedelta(hours=2)):
            meta3 = self.mgr.create(data3)

        # 搜索特定時間範圍
        query = ResourceMetaSearchQuery(
            created_time_start=base_time + dt.timedelta(minutes=30),
            created_time_end=base_time + dt.timedelta(hours=1, minutes=30),
        )
        search_user, search_now = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(search_user, search_now):
            results = self.mgr.search_resources(query)
        results_id = [meta.resource_id for meta in results]

        # 只有 meta2 應該在範圍內
        assert meta2.resource_id in results_id
        assert meta1.resource_id not in results_id
        assert meta3.resource_id not in results_id

    def test_search_resources_with_sorting(self):
        """測試排序功能"""
        # 創建多個資源用於排序測試
        base_time = dt.datetime(2023, 1, 1, 12, 0, 0)
        metas: list[ResourceMeta] = []

        for i in range(3):
            data = new_data()
            user = f"user_{i}"
            create_time = base_time + dt.timedelta(hours=i)
            with self.mgr.meta_provide(user, create_time):
                meta = self.mgr.create(data)
                metas.append(meta)

        # 按創建時間升序排列
        sort_asc = ResourceMetaSearchSort(
            key=ResourceMetaSortKey.created_time,
            direction=ResourceMetaSortDirection.ascending,
        )
        query = ResourceMetaSearchQuery(sorts=[sort_asc])
        search_user, search_now = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(search_user, search_now):
            results_asc = self.mgr.search_resources(query)

        # 按創建時間降序排列
        sort_desc = ResourceMetaSearchSort(
            key=ResourceMetaSortKey.created_time,
            direction=ResourceMetaSortDirection.descending,
        )
        query = ResourceMetaSearchQuery(sorts=[sort_desc])
        with self.mgr.meta_provide(search_user, search_now):
            results_desc = self.mgr.search_resources(query)

        # 降序結果應該與升序結果相反
        assert results_asc == results_desc[::-1]
        # 都應該包含所有資源ID
        expected_ids = {meta.resource_id for meta in metas}
        assert {r.resource_id for r in results_asc} == expected_ids
        assert {r.resource_id for r in results_desc} == expected_ids

    def test_search_resources_complex_query(self):
        """測試複雜搜索查詢"""
        # 創建測試數據
        base_time = dt.datetime(2023, 1, 1, 12, 0, 0)
        user1, user2 = "alice", "bob"

        # Alice 創建兩個資源
        data1 = new_data()
        with self.mgr.meta_provide(user1, base_time):
            meta1 = self.mgr.create(data1)

        data2 = new_data()
        with self.mgr.meta_provide(user1, base_time + dt.timedelta(hours=1)):
            meta2 = self.mgr.create(data2)

        # Bob 創建一個資源
        data3 = new_data()
        with self.mgr.meta_provide(user2, base_time + dt.timedelta(minutes=30)):
            meta3 = self.mgr.create(data3)

        # 刪除其中一個資源
        with self.mgr.meta_provide(user1, base_time + dt.timedelta(hours=2)):
            self.mgr.delete(meta1.resource_id)

        # 複雜查詢：Alice 創建的、未刪除的、在特定時間範圍內的資源
        query = ResourceMetaSearchQuery(
            is_deleted=False,
            created_bys=[user1],
            created_time_start=base_time,
            created_time_end=base_time + dt.timedelta(hours=2),
        )
        search_user, search_now = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(search_user, search_now):
            results = self.mgr.search_resources(query)
        results_id = [meta.resource_id for meta in results]

        # 只有 meta2 應該匹配（Alice 創建、未刪除、在時間範圍內）
        assert meta2.resource_id in results_id
        assert meta1.resource_id not in results_id  # 已刪除
        assert meta3.resource_id not in results_id  # 不是 Alice 創建的

    def test_search_resources_empty_results(self):
        """測試沒有匹配結果的搜索"""
        # 創建一個資源
        data = new_data()
        user, now, meta = self.create(data)

        # 搜索不存在的用戶創建的資源
        query = ResourceMetaSearchQuery(created_bys=["nonexistent_user"])
        search_user, search_now = faker.user_name(), faker.date_time()
        with self.mgr.meta_provide(search_user, search_now):
            results = self.mgr.search_resources(query)

        assert len(results) == 0
        assert isinstance(results, list)


@pytest.mark.parametrize("default_status", ["stable", "draft"])
class TestDefaultStatus:
    @pytest.fixture(autouse=True)
    def setup_method(
        self,
        default_status: str,
    ):
        self.default_status = default_status
        meta_store = get_meta_store("memory")
        with get_resource_store("memory") as resource_store:
            storage = SimpleStorage(
                meta_store=meta_store,
                resource_store=resource_store,
            )
            self.mgr = ResourceManager(
                Data, storage=storage, default_status=default_status
            )
            yield

    def create(self, data: Data, *, status: RevisionStatus | UnsetType = UNSET):
        user = faker.user_name()
        now = faker.date_time()
        with self.mgr.meta_provide(user, now):
            meta = self.mgr.create(data, status=status)
        return user, now, meta

    def test_create(self):
        data = new_data()
        user, now, meta = self.create(data)
        got = self.mgr.get(meta.resource_id)
        assert got.info.status == self.default_status

    def test_update(self):
        data = new_data()
        user, now, meta = self.create(data, status="draft")
        u_data = new_data()
        u_user = faker.user_name()
        u_now = faker.date_time()
        with self.mgr.meta_provide(u_user, u_now):
            u_meta = self.mgr.update(meta.resource_id, u_data)
        got = self.mgr.get(meta.resource_id)
        assert u_meta.status == self.default_status
        assert got.info.status == self.default_status


@pytest.fixture
def my_tmpdir():
    """Fixture to provide a temporary directory for testing."""
    import tempfile

    with tempfile.TemporaryDirectory(dir="./") as d:
        yield Path(d)


@pytest.mark.parametrize(
    "store_type",
    [
        "memory",
        "memory-pg",
        "sql3-mem",
        "sql3-file",
        "disk-sql3file",
        "redis",
        "dfm",
        "disk",
        "redis-pg",
    ],
)
class TestMetaStore:
    @pytest.fixture(autouse=True)
    def setup_method(
        self,
        store_type: str,
        my_tmpdir: str,
    ):
        self.meta_store = get_meta_store(store_type, tmpdir=my_tmpdir)
        self.store_type = store_type

    @pytest.mark.benchmark
    @pytest.mark.slow
    def test_large_size_behavior(self):
        def get_fake_meta():
            return ResourceMeta(
                resource_id=str(uuid4()),
                current_revision_id=str(uuid4()),
                total_revision_count=1,
                created_time=dt.datetime.now(),
                created_by="a",
                updated_time=dt.datetime.now(),
                updated_by="a",
            )

        expected_spec = {
            "memory": {
                "size": 1000000,
                "create_time": dt.timedelta(seconds=1),
                "search_time": dt.timedelta(milliseconds=400),
                "search_wait": dt.timedelta(seconds=0),
            },
            "sql3-mem": {
                "size": 100000,
                "create_time": dt.timedelta(seconds=3.2),
                "search_time": dt.timedelta(milliseconds=0.8),
                "search_wait": dt.timedelta(seconds=0),
            },
            "memory-pg": {
                "size": 100000,
                "create_time": dt.timedelta(seconds=0.12),
                "search_time": dt.timedelta(milliseconds=4),
                "search_wait": dt.timedelta(seconds=10),
            },
            "dfm": {
                "size": 100000,
                "create_time": dt.timedelta(seconds=0.45),
                "search_time": dt.timedelta(milliseconds=40),
                "search_wait": dt.timedelta(seconds=0),
            },
            "sql3-file": {
                "size": 10000,
                "create_time": dt.timedelta(seconds=15),
                "search_time": dt.timedelta(milliseconds=0.8),
                "search_wait": dt.timedelta(seconds=0),
            },
            "disk": {
                "size": 100000,
                "create_time": dt.timedelta(seconds=3.3),
                "search_time": dt.timedelta(seconds=1.6),
                "search_wait": dt.timedelta(seconds=0),
            },
            "disk-sql3file": {
                "size": 100000,
                "create_time": dt.timedelta(seconds=5.8),
                "search_time": dt.timedelta(milliseconds=5),
                "search_wait": dt.timedelta(seconds=10),
            },
            "redis": {
                "size": 100000,
                "create_time": dt.timedelta(seconds=8),
                "search_time": dt.timedelta(milliseconds=6800),
                "search_wait": dt.timedelta(seconds=0),
            },
            "redis-pg": {
                "size": 100000,
                "create_time": dt.timedelta(seconds=12),
                "search_time": dt.timedelta(milliseconds=4.2),
                "search_wait": dt.timedelta(seconds=2),
            },
        }
        minimum_time_rate = 0.6  # time should be at least x% of expected time

        trials = expected_spec[self.store_type]["size"]
        expected_create_time = expected_spec[self.store_type]["create_time"]
        expected_search_time = expected_spec[self.store_type]["search_time"]
        search_wait = expected_spec[self.store_type]["search_wait"]

        all_meta: list[ResourceMeta] = []
        tt = dt.timedelta(0)
        for _ in range(trials):
            meta = get_fake_meta()
            all_meta.append(meta)
            st = dt.datetime.now()
            self.meta_store[meta.resource_id] = meta
            tt += dt.datetime.now() - st
        assert expected_create_time * minimum_time_rate < tt < expected_create_time, (
            f"Benchmark failed, took {tt.total_seconds()} seconds"
        )

        times = sorted(all_meta, key=lambda x: x.created_time)[567 : 567 + 1000]

        metas_by_time = sorted(times, key=lambda x: x.resource_id)

        time.sleep(search_wait.total_seconds())
        st = dt.datetime.now()
        got = [
            k
            for k in self.meta_store.iter_search(
                ResourceMetaSearchQuery(
                    created_time_start=times[0].created_time,
                    created_time_end=times[-1].created_time,
                    sorts=[
                        ResourceMetaSearchSort(
                            key=ResourceMetaSortKey.resource_id,
                            direction=ResourceMetaSortDirection.ascending,
                        ),
                    ],
                ),
            )
        ]
        tt = dt.datetime.now() - st
        assert got == metas_by_time[:10]
        assert expected_search_time * minimum_time_rate < tt < expected_search_time
