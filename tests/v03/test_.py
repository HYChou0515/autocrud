from msgspec import Struct
import pytest
from autocrud.v03.core import Resource, ResourceManager
import datetime as dt
from faker import Faker

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
            faker.pystr(): new_inner_data() for _ in faker.pylist(variable_nb_elements=True)
        }
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
        assert got.meta == meta
        assert got.meta.created_by == user
        assert got.meta.updated_by == user
        assert got.meta.created_time == now
        assert got.meta.updated_time == now
        assert got.meta.status == "stable"
        assert got.meta.last_revision_id == ""
        assert got.meta.schema_version == ""
        assert got.meta.uid
        assert got.meta.resource_id
        res_meta = self.mgr.get_meta(meta.resource_id)
        assert res_meta.current_revision_id == got.meta.revision_id
        assert res_meta.resource_id == got.meta.resource_id
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
        assert got.meta == u_meta
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
    