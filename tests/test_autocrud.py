from unittest.mock import Mock
from msgspec import Struct
import pytest

from autocrud.crud.core import AutoCRUD
from autocrud.crud.route_templates.get import ReadRouteTemplate
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

    def test_apply_router_templates_order(self):
        applied = []

        class MockRouteTemplate(ReadRouteTemplate):
            def apply(self, *args, **kwargs):
                applied.append(self.order)

        templates = [
            MockRouteTemplate(order=1),
            MockRouteTemplate(order=2),
            MockRouteTemplate(order=5),
        ]
        crud = AutoCRUD(route_templates=templates.copy())
        crud.add_model(User)
        crud.apply(Mock())
        crud.add_route_template(MockRouteTemplate(order=4))
        crud.apply(Mock())
        assert applied == [1, 2, 5, 1, 2, 4, 5]

    @pytest.mark.parametrize("default_status", ["stable", "draft", None])
    def test_add_model_with_default_status(self, default_status: str | None):
        crud = AutoCRUD()
        crud.add_model(User, default_status=default_status)
        mgr = crud.get_resource_manager(User)
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create({"name": "Alice", "age": 30})
        assert info.status == (default_status or "stable")
