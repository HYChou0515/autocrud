"""``default_is_deleted`` controls whether programmatic list/count/iter include
soft-deleted resources when the query doesn't say.

Default (``None``) keeps the current behaviour — no filter, so soft-deleted rows
are included (non-breaking). ``False`` excludes them (matching the HTTP
``GET /{model}`` default); ``True`` returns only deleted. An explicit
``is_deleted`` in the query always wins.
"""

import msgspec

from specstar import SpecStar
from specstar.query_types import ResourceMetaSearchQuery


class Item(msgspec.Struct):
    name: str


def _rm(**cfg):
    sp = SpecStar()
    sp.configure(default_user="t", **cfg)
    sp.add_model(Item, name="item")
    rm = sp.get_resource_manager(Item)
    a = rm.create(Item(name="alpha")).resource_id
    rm.create(Item(name="beta"))
    rm.delete(a)  # soft-delete "alpha"
    return rm


def _names(items):
    return sorted(x.data.name for x in items)


def test_default_is_deleted_false_excludes_soft_deleted():
    rm = _rm(default_is_deleted=False)
    assert _names(rm.list_resources()) == ["beta"]


def test_default_none_is_non_breaking_includes_soft_deleted():
    rm = _rm()  # unset → current behaviour
    assert _names(rm.list_resources()) == ["alpha", "beta"]


def test_explicit_query_is_deleted_overrides_the_default():
    rm = _rm(default_is_deleted=False)
    only_deleted = rm.list_resources(ResourceMetaSearchQuery(is_deleted=True))
    assert _names(only_deleted) == ["alpha"]  # explicit wins over default=False


def test_default_is_deleted_applies_to_count_and_iter():
    rm = _rm(default_is_deleted=False)
    assert rm.count_resources() == 1  # excludes the soft-deleted alpha
    assert len(list(rm.iter_all())) == 1  # iter_all honours it too


def test_default_is_deleted_true_returns_only_deleted():
    rm = _rm(default_is_deleted=True)
    assert _names(rm.list_resources()) == ["alpha"]
