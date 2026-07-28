"""Deleting revisions must not ask about each uid separately.

Both hard-delete paths remove index rows, then drop the data rows nothing
references any more. That check ran per uid — `SELECT 1 ... WHERE uid = %s` then
maybe a `DELETE`, two round-trips each — so pruning a resource cost statements
proportional to its revision count (measured: 49 for 7 revisions, #442).

"delete the rows no index references" is one statement, and SQL is where that
belongs: doing it per uid also races, since another writer can add a reference
between the check and the delete.
"""

from unittest.mock import MagicMock, patch

import pytest

REG = "specstar.resource_manager._pg_pool"


@pytest.fixture(autouse=True)
def _reset_registry():
    from specstar.resource_manager import _pg_pool

    _pg_pool.close_all_pools()
    yield
    _pg_pool.close_all_pools()


def _store_and_cursor(uids):
    cursor = MagicMock(name="cursor")
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.fetchall.return_value = [(u,) for u in uids]
    calls = {"n": 0}

    def _fetchone():
        calls["n"] += 1
        return [1] if calls["n"] == 1 else None  # first is the SELECT 1 health check

    cursor.fetchone.side_effect = _fetchone

    conn = MagicMock(name="conn")
    conn.cursor.return_value = cursor
    pool = MagicMock(name="pool")
    pool.getconn.return_value = conn

    with patch(f"{REG}.get_pool", return_value=pool):
        with patch(
            "specstar.resource_manager.resource_store.postgres."
            "PostgresResourceStore._init_tables"
        ):
            from specstar.resource_manager.resource_store.postgres import (
                PostgresResourceStore,
            )

            store = PostgresResourceStore(pg_dsn="postgresql://fake/fake")
    return store, cursor


def _per_uid_probes(cursor):
    return [
        c
        for c in cursor.execute.call_args_list
        if "WHERE uid = %s LIMIT 1" in str(c.args[0] if c.args else "")
    ]


def test_purge_does_not_probe_each_uid():
    store, cursor = _store_and_cursor(["u1", "u2", "u3", "u4"])
    store.purge_resource("r1")
    assert _per_uid_probes(cursor) == [], cursor.execute.call_args_list


def test_delete_revisions_does_not_probe_each_uid():
    store, cursor = _store_and_cursor(["u1", "u2", "u3", "u4"])
    store.delete_revisions("r1", ["rev1", "rev2"])
    assert _per_uid_probes(cursor) == [], cursor.execute.call_args_list
