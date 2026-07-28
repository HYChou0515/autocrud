"""An update must not read the previous row for an encoder that isn't there.

`update` fetched the previous revision's data on every call so the embedding
processor could reuse a cached vector. A model with no `Embedding` field never
uses it — `process_sync` loops over an empty field list — so the read, the
decode of the whole previous row, and (on a SQL backend) its round-trips are
spent producing an argument nobody looks at.

Measured against a local postgres: one `update` cost 19 SQL statements, two of
them this read (#442).
"""

import msgspec

from specstar import SpecStar


class Plain(msgspec.Struct):
    """No Embedding field — the common case."""

    title: str


def _manager():
    sp = SpecStar()
    sp.configure(default_user="t")
    sp.add_model(Plain, name="plain")
    return sp.get_resource_manager(Plain)


def test_update_of_a_model_without_embeddings_does_not_read_the_previous_data():
    rm = _manager()
    rid = rm.create(Plain(title="a")).resource_id

    reads: list[str] = []
    storage = rm.storage
    original = type(storage).get_data_bytes

    def counting(self, resource_id, revision_id, schema_version=msgspec.UNSET, *a, **k):  # noqa: ANN001
        reads.append(resource_id)
        return original(self, resource_id, revision_id, schema_version, *a, **k)

    type(storage).get_data_bytes = counting  # ty: ignore[invalid-assignment]
    try:
        rm.update(rid, Plain(title="b"))
    finally:
        type(storage).get_data_bytes = original

    assert reads == [], reads
    assert rm.get(rid).data.title == "b"  # and the update still happened


def test_update_reads_the_resource_meta_once():
    """`update` loads the meta, then asks for the previous revision's info
    without saying which schema version — so the storage facade loads the same
    meta again to resolve it, from a caller that is already holding it.

    Two identical `SELECT ... WHERE resource_id = ...` per update, plus the
    connection checkout each one takes.
    """
    rm = _manager()
    rid = rm.create(Plain(title="a")).resource_id

    loads: list[str] = []
    storage = rm.storage
    original = type(storage).get_meta

    def counting(self, resource_id, *a, **k):  # noqa: ANN001
        loads.append(resource_id)
        return original(self, resource_id, *a, **k)

    type(storage).get_meta = counting  # ty: ignore[invalid-assignment]
    try:
        rm.update(rid, Plain(title="b"))
    finally:
        type(storage).get_meta = original

    assert len(loads) == 1, f"meta loaded {len(loads)} times: {loads}"


def test_revision_exists_checks_the_resource_once():
    """`revision_exists` loaded the meta, then asked the meta store AGAIN whether
    the resource is there — but the load already answered that: it raises for an
    unknown id, so reaching the second check proves the first succeeded.

    Two `SELECT ... WHERE resource_id = ...` and two connection checkouts to
    answer one question.
    """
    rm = _manager()
    rid = rm.create(Plain(title="a")).resource_id
    rev = rm.get_meta(rid).current_revision_id

    probes: list[str] = []
    store = rm.storage._meta_store
    original_get = type(store).__getitem__
    original_in = type(store).__contains__

    def counting_get(self, key):  # noqa: ANN001
        probes.append(f"get:{key}")
        return original_get(self, key)

    def counting_in(self, key):  # noqa: ANN001
        probes.append(f"in:{key}")
        return original_in(self, key)

    type(store).__getitem__ = counting_get  # ty: ignore[invalid-assignment]
    type(store).__contains__ = counting_in  # ty: ignore[invalid-assignment]
    try:
        assert rm.revision_exists(rid, rev) is True
    finally:
        type(store).__getitem__ = original_get
        type(store).__contains__ = original_in

    assert len(probes) == 1, f"meta store hit {len(probes)} times: {probes}"
