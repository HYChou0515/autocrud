"""Programmatic writes without an operation context follow HTTP's behavior.

In non-strict mode (the default) a ``mgr.create()`` with no ``using()`` and no
configured ``default_user`` / ``default_now`` falls back to ``"anonymous"`` +
``now()`` — exactly what an unauthenticated HTTP request records — instead of
leaking a raw ``LookupError``. ``strict_operation_context=True`` restores the
hard failure (a friendly ``MissingOperationContextError``).
"""

import datetime as dt

import msgspec
import pytest

from specstar import Schema, SpecStar
from specstar.types import MissingOperationContextError


class Item(msgspec.Struct):
    name: str


def test_programmatic_create_without_context_defaults_to_anonymous():
    sp = SpecStar()  # non-strict default; no default_user / default_now
    sp.add_model(Schema(Item, "v1"))
    mgr = sp.get_resource_manager(Item)

    info = mgr.create(Item(name="x"))
    assert mgr.get_meta(info.resource_id).created_by == "anonymous"


def test_now_defaults_to_current_time_without_context():
    sp = SpecStar()
    sp.add_model(Schema(Item, "v1"))
    mgr = sp.get_resource_manager(Item)

    before = dt.datetime.now(dt.timezone.utc)
    info = mgr.create(Item(name="x"))
    created = mgr.get_meta(info.resource_id).created_time
    assert isinstance(created, dt.datetime)
    # populated from now() rather than left unset / erroring
    assert (created - before).total_seconds() == pytest.approx(0, abs=5)


def test_strict_mode_still_raises_without_context():
    sp = SpecStar(strict_operation_context=True)
    sp.add_model(Schema(Item, "v1"))
    mgr = sp.get_resource_manager(Item)

    with pytest.raises(MissingOperationContextError):
        mgr.create(Item(name="x"))
