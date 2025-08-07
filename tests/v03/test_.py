from msgspec import Struct
import msgspec
import pytest
from autocrud.v03.core import ResourceManager
import datetime as dt
from faker import Faker
import jsonpatch


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


class Test:
    @pytest.fixture(autouse=True)
    def setup_method(self):
        self.mgr = ResourceManager[Data](Data)

    def create(self, data: Data):
        user = faker.user_name()
        now = faker.date_time()
        with self.mgr.meta_provide(user, now):
            meta = self.mgr.create(data)
        return user, now, meta

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
        assert got.info.last_revision_id == ""
        assert got.info.schema_version == ""
        assert got.info.uid
        assert got.info.resource_id
        res_meta = self.mgr.get_meta(meta.resource_id)
        assert res_meta.current_revision_id == got.info.revision_id
        assert res_meta.resource_id == got.info.resource_id
        assert res_meta.total_revision_count == 1
        assert res_meta.valid_revision_count == 1
        assert res_meta.created_time == now
        assert res_meta.created_by == user
        assert res_meta.updated_time == now
        assert res_meta.updated_by == user

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
        assert u_meta.last_revision_id == meta.revision_id
        assert u_meta.schema_version == ""
        assert u_meta.data_hash == ""
        assert u_meta.status == "stable"
        assert u_meta.created_time == u_now
        assert u_meta.updated_time == u_now
        assert u_meta.created_by == u_user
        assert u_meta.updated_by == u_user
        got = self.mgr.get(meta.resource_id)
        assert got.info == u_meta
        assert got.data == u_data
        res_meta = self.mgr.get_meta(meta.resource_id)
        assert res_meta.current_revision_id == u_meta.revision_id
        assert res_meta.resource_id == u_meta.resource_id
        assert res_meta.total_revision_count == 2
        assert res_meta.valid_revision_count == 2
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
        assert p_meta.last_revision_id == meta.revision_id
        assert p_meta.schema_version == ""
        assert p_meta.data_hash == ""
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
        res_meta = self.mgr.get_meta(meta.resource_id)
        assert res_meta.current_revision_id == p_meta.revision_id
        assert res_meta.resource_id == p_meta.resource_id
        assert res_meta.total_revision_count == 2
        assert res_meta.valid_revision_count == 2
        assert res_meta.created_time == now
        assert res_meta.created_by == user
        assert res_meta.updated_time == p_now
        assert res_meta.updated_by == p_user
