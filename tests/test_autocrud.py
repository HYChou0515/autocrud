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

    @pytest.mark.parametrize("level", ["crud", "model"])
    def test_add_model_with_default_user(self, level: str):
        if level == "crud":
            crud = AutoCRUD(default_user="system")
            crud.add_model(User)
        else:
            crud = AutoCRUD(default_user="foo")
            crud.add_model(User, default_user="system")
        mgr = crud.get_resource_manager(User)
        with mgr.meta_provide(now=dt.datetime.now()):
            info = mgr.create({"name": "Alice", "age": 30})
        assert info.created_by == "system"

    def test_add_model_without_default_user(self):
        crud = AutoCRUD()
        crud.add_model(User)
        mgr = crud.get_resource_manager(User)
        with pytest.raises(LookupError):
            with mgr.meta_provide(now=dt.datetime.now()):
                mgr.create({"name": "Alice", "age": 30})

    @pytest.mark.parametrize("level", ["crud", "model"])
    def test_add_model_with_default_now(self, level: str):
        if level == "crud":
            crud = AutoCRUD(default_now=lambda: dt.datetime(2023, 1, 1))
            crud.add_model(User)
        else:
            crud = AutoCRUD(default_now=lambda: dt.datetime(2024, 1, 1))
            crud.add_model(User, default_now=lambda: dt.datetime(2023, 1, 1))
        mgr = crud.get_resource_manager(User)
        with mgr.meta_provide("system"):
            info = mgr.create({"name": "Alice", "age": 30})
        assert info.created_time == dt.datetime(2023, 1, 1)

    def test_add_model_without_default_now(self):
        crud = AutoCRUD()
        crud.add_model(User)
        mgr = crud.get_resource_manager(User)
        with pytest.raises(LookupError):
            with mgr.meta_provide("system"):
                mgr.create({"name": "Alice", "age": 30})

    def test_add_model_with_default_user_and_now(self):
        crud = AutoCRUD()
        crud.add_model(User, default_user="system", default_now=dt.datetime.now)
        mgr = crud.get_resource_manager(User)
        info = mgr.create({"name": "Alice", "age": 30})
        assert info.created_time - dt.datetime.now() < dt.timedelta(seconds=1)
        assert info.created_by == "system"
