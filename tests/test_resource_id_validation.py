"""A caller-supplied ``resource_id`` must be safe in file paths and URLs.

``create(data, resource_id=...)`` accepts a custom id, but ids with path
separators or control chars break disk storage (FileNotFoundError) and can't be
addressed over HTTP (``/{model}/{resource_id}`` is a single segment). So they're
rejected up front, backend-agnostically, with a clear ValidationError.
"""

import msgspec
import pytest

from specstar import SpecStar
from specstar.errors import ValidationError


class W(msgspec.Struct):
    name: str


def _mgr():
    sp = SpecStar()
    sp.configure(default_user="t")  # in-memory store
    sp.add_model(W, name="w")
    return sp.get_resource_manager(W)


def test_create_rejects_slash_in_resource_id():
    mgr = _mgr()
    with pytest.raises(ValidationError):
        mgr.create(W(name="x"), resource_id="a/b")


def test_create_rejects_backslash_and_control_and_empty():
    mgr = _mgr()
    for bad in ("a\\b", "a\nb", "", "   "):
        with pytest.raises(ValidationError):
            mgr.create(W(name="x"), resource_id=bad)


def test_create_accepts_a_safe_custom_id():
    mgr = _mgr()
    info = mgr.create(W(name="x"), resource_id="my-custom_1")
    assert mgr.get(info.resource_id).data.name == "x"  # round-trips


def test_disk_storage_slash_gives_clear_error_not_filenotfound(tmp_path):
    # The original bug: on disk this raised a confusing FileNotFoundError.
    from specstar.resource_manager.storage_factory import DiskStorageFactory

    sp = SpecStar()
    sp.configure(storage_factory=DiskStorageFactory(str(tmp_path)), default_user="t")
    sp.add_model(W, name="w")
    mgr = sp.get_resource_manager(W)
    with pytest.raises(ValidationError):
        mgr.create(W(name="x"), resource_id="a/b")
