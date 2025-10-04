import io
import os
from pathlib import Path
import datetime as dt
import pytest
from msgspec import Struct

from autocrud.crud.core import AutoCRUD
from autocrud.resource_manager.storage_factory import DiskStorageFactory


class User(Struct):
    name: str
    age: int


@pytest.fixture
def my_tmpdir():
    """Fixture to provide a temporary directory for testing."""
    import tempfile

    with tempfile.TemporaryDirectory(dir="./") as d:
        yield Path(d)


class TestAutocrudDumpLoad:
    """Test IMetaStore.iter_search method with different storage types."""

    @pytest.fixture(autouse=True)
    def setup_method(self, my_tmpdir):
        os.makedirs(my_tmpdir / "1", exist_ok=True)
        os.makedirs(my_tmpdir / "2", exist_ok=True)
        self.crud1 = AutoCRUD(storage_factory=DiskStorageFactory(my_tmpdir / "1"))
        self.crud2 = AutoCRUD(storage_factory=DiskStorageFactory(my_tmpdir / "2"))
        self.crud1.add_model(User)
        self.crud2.add_model(User)

    def _add_users(self, crud: AutoCRUD):
        users = [
            User(name="Alice", age=30),
            User(name="Bob", age=25),
            User(name="Charlie", age=35),
            User(name="David", age=40),
        ]
        mgr = crud.get_resource_manager(User)
        with mgr.meta_provide("user", dt.datetime.now()):
            for user in users:
                mgr.create(user)

    def test_dump_empty(self):
        bio1 = io.BytesIO()
        bio2 = io.BytesIO()
        self.crud1.dump(bio1)
        self.crud2.dump(bio2)
        assert bio1.getvalue() == bio2.getvalue()

    def test_dump_and_load(self):
        self._add_users(self.crud1)
        bio1 = io.BytesIO()
        self.crud1.dump(bio1)
        bio1.seek(0)
        self.crud2.load(bio1)
        bio2 = io.BytesIO()
        self.crud2.dump(bio2)
        assert bio1.getvalue() == bio2.getvalue()
