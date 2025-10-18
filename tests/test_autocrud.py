from msgspec import Struct

from autocrud.crud.core import AutoCRUD
from autocrud.resource_manager.basic import Encoding
import datetime as dt


class User(Struct):
    name: str
    age: int
    wage: int | None = None
    books: list[str] = []


class TestAutocrud:
    def test_add_model_with_encoding(self):
        crud = AutoCRUD()
        crud.add_model(User)
        assert (
            crud.get_resource_manager(User)._data_serializer.encoding == Encoding.json
        )

        crud = AutoCRUD(encoding=Encoding.msgpack)
        crud.add_model(User)
        assert (
            crud.get_resource_manager(User)._data_serializer.encoding
            == Encoding.msgpack
        )

        crud = AutoCRUD(encoding=Encoding.json)
        crud.add_model(User, encoding=Encoding.msgpack)
        assert (
            crud.get_resource_manager(User)._data_serializer.encoding
            == Encoding.msgpack
        )

        crud = AutoCRUD()
        crud.add_model(User, encoding=Encoding.msgpack)
        assert (
            crud.get_resource_manager(User)._data_serializer.encoding
            == Encoding.msgpack
        )

    def test_add_model_with_name(self):
        crud = AutoCRUD()
        crud.add_model(User, name="xx")
        assert crud.get_resource_manager("xx").resource_name == "xx"
        mgr = crud.get_resource_manager("xx")
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create({"name": "Alice", "age": 30})
        assert info.resource_id.startswith("xx:")

    def test_add_model_with_index_fields(self):
        crud = AutoCRUD()
        crud.add_model(User, indexed_fields=[("wage", int | None)])
        crud.add_model(User, name="u2", indexed_fields=[("books", list[str])])
        # no error raised
