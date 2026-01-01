from unittest.mock import Mock
from msgspec import Struct, to_builtins
import pytest
from jsonpointer import JsonPointer

from autocrud.crud.core import AutoCRUD
from autocrud.crud.route_templates.get import ReadRouteTemplate
from autocrud.resource_manager.basic import Encoding
import datetime as dt

from autocrud.types import IResourceManager, RevisionInfo


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


class Manager(User):
    slaves: list["Manager"] = []
    boss: User | None = None


class TestAutocrudGetPartial:
    @pytest.fixture(autouse=True)
    def setup_method(self):
        self.crud = AutoCRUD()
        self.crud.add_model(Manager, default_user="system", default_now=dt.datetime.now)
        self.crud.add_model(User, default_user="system", default_now=dt.datetime.now)

    def _check(
        self,
        mgr: IResourceManager,
        info: RevisionInfo,
        partial: list[JsonPointer],
        expected: dict,
    ):
        d = mgr.get_partial(
            info.resource_id,
            info.revision_id,
            partial=partial,
        )
        assert to_builtins(d) == expected

    def test_get_with_revision_id(self):
        mgr = self.crud.get_resource_manager(Manager)
        info = mgr.create({"name": "Alice", "age": 30})
        assert mgr.get(info.resource_id) == mgr.get(
            info.resource_id, revision_id=info.revision_id
        )

    def test_get_partial(self):
        mgr = self.crud.get_resource_manager(Manager)
        info = mgr.create(
            {
                "name": "Alice",
                "age": 30,
                "slaves": [{"name": "Bob", "age": 25}, {"name": "Charlie", "age": 28}],
                "boss": {"name": "Diana", "age": 40},
            }
        )

        self._check(
            mgr,
            info,
            [JsonPointer("/name"), JsonPointer("/slaves/0/age")],
            {"name": "Alice", "slaves": [{"age": 25}]},
        )

        self._check(
            mgr,
            info,
            ["name", "boss", "slaves/-/name"],
            {
                "name": "Alice",
                "boss": {"name": "Diana", "age": 40, "wage": None, "books": []},
                "slaves": [{"name": "Bob"}, {"name": "Charlie"}],
            },
        )

        self._check(
            mgr,
            info,
            ["slaves"],
            {
                "slaves": [
                    {
                        "age": 25,
                        "name": "Bob",
                        "wage": None,
                        "books": [],
                        "slaves": [],
                        "boss": None,
                    },
                    {
                        "age": 28,
                        "name": "Charlie",
                        "wage": None,
                        "books": [],
                        "slaves": [],
                        "boss": None,
                    },
                ]
            },
        )

    def test_get_partial_slicing11(self):
        mgr = self.crud.get_resource_manager(Manager)
        slaves = [
            {"name": "Bob", "age": 25},
            {"name": "Charlie", "age": 28},
            {"name": "Dave", "age": 30},
            {"name": "Eve", "age": 22},
        ]
        slaves[1]["slaves"] = [
            {"name": "Bob Jr.", "age": 5},
            {"name": "Bob III", "age": 3},
        ]
        info = mgr.create({"name": "Alice", "age": 30, "slaves": slaves})

        self._check(
            mgr,
            info,
            ["slaves/:2/name", "slaves/1:2/slaves/-/name", "slaves/1:/age"],
            {
                "slaves": [
                    {"name": "Bob"},
                    {
                        "name": "Charlie",
                        "age": 28,
                        "slaves": [{"name": "Bob Jr."}, {"name": "Bob III"}],
                    },
                    {"age": 30},
                    {"age": 22},
                ]
            },
        )

    def test_get_partial_slicing1(self):
        mgr = self.crud.get_resource_manager(Manager)
        slaves = [
            {"name": "Bob", "age": 25},
            {"name": "Charlie", "age": 28},
            {"name": "Dave", "age": 30},
            {"name": "Eve", "age": 22},
        ]
        slaves[0]["slaves"] = [
            {"name": "Bob Jr.", "age": 5},
            {"name": "Bob III", "age": 3},
        ]
        slaves[0]["boss"] = {"name": "Bob Sr.", "age": 55}
        slaves[1]["boss"] = {"name": "Charlie Sr.", "age": 50}
        info = mgr.create({"name": "Alice", "age": 30, "slaves": slaves})

        self._check(
            mgr,
            info,
            ["slaves/:2/slaves/1:/age", "slaves/1:/boss/age"],
            {
                "slaves": [
                    {"slaves": [{"age": 3}]},
                    {"boss": {"age": 50}, "slaves": []},
                    {"boss": None},
                    {"boss": None},
                ]
            },
        )

    def test_get_partial_slicing(self):
        mgr = self.crud.get_resource_manager(Manager)
        info = mgr.create(
            {
                "name": "Alice",
                "age": 30,
                "slaves": [
                    {"name": "Bob", "age": 25},
                    {"name": "Charlie", "age": 28},
                    {"name": "Dave", "age": 30},
                    {"name": "Eve", "age": 22},
                ],
            }
        )

        cases = [
            (["slaves/:2/name"], {"slaves": [{"name": "Bob"}, {"name": "Charlie"}]}),
            (["slaves/1:3/name"], {"slaves": [{"name": "Charlie"}, {"name": "Dave"}]}),
            (["slaves/::2/name"], {"slaves": [{"name": "Bob"}, {"name": "Dave"}]}),
            (
                ["slaves/0/name", "slaves/3/age"],
                {"slaves": [{"name": "Bob"}, {"age": 22}]},
            ),
            (
                ["slaves/-/age"],
                {"slaves": [{"age": 25}, {"age": 28}, {"age": 30}, {"age": 22}]},
            ),
            (
                ["slaves/:/age"],
                {"slaves": [{"age": 25}, {"age": 28}, {"age": 30}, {"age": 22}]},
            ),
            (["slaves/1::2/age"], {"slaves": [{"age": 28}, {"age": 22}]}),
            (["slaves/1:3:2/age"], {"slaves": [{"age": 28}]}),
            (
                ["slaves/:/age", "slaves/:/name"],
                {
                    "slaves": [
                        {"age": 25, "name": "Bob"},
                        {"age": 28, "name": "Charlie"},
                        {"age": 30, "name": "Dave"},
                        {"age": 22, "name": "Eve"},
                    ]
                },
            ),
            (
                ["slaves/:/age", "slaves/:/name", "slaves/1::2/wage"],
                {
                    "slaves": [
                        {"age": 25, "name": "Bob"},
                        {"age": 28, "name": "Charlie", "wage": None},
                        {"age": 30, "name": "Dave"},
                        {"age": 22, "name": "Eve", "wage": None},
                    ]
                },
            ),
        ]

        for partial, expected in cases:
            self._check(mgr, info, partial, expected)

    def test_get_needs_pruning(self):
        from autocrud.resource_manager.partial import _needs_pruning

        assert not _needs_pruning([["name"], ["age"]])
        assert _needs_pruning([["slaves", "0", "name"]])
        assert not _needs_pruning([["slaves", ":", "name"]])
        assert _needs_pruning([["slaves", "1:3", "name"]])
        assert _needs_pruning([["slaves", "::2", "name"]])
        assert not _needs_pruning([["slaves", "-", "name"]])
