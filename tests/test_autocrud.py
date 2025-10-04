from msgspec import Struct

from autocrud.crud.core import AutoCRUD
from autocrud.resource_manager.basic import Encoding


class User(Struct):
    name: str
    age: int


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
