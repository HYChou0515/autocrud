"""A failed sort-index build must never take the application down (#422 follow-up).

``ensure_sort_index`` runs from ``add_model``, i.e. on the boot path of every
process. Its whole premise — stated in its own docstring, and the reason #418 was
built as an index rather than a column — is that the index is DERIVED metadata:
present it is fast, absent it is slow, and nothing else changes. A build that
fails must therefore degrade to "slow", never to "down".

It did not. ``CREATE INDEX CONCURRENTLY`` can fail for reasons that have nothing
to do with the caller — a statement_timeout, a cancelled backend, the pod being
killed mid-rollout, disk pressure — and the exception propagated straight out of
``add_model``. Worse, a killed build leaves an INVALID index behind, which the
repair path only reaches on the NEXT boot: if the environment reliably kills the
build (a global timeout, a large table), every boot raises and the repair is
never reached. That is a crash loop, caused by an index that was only ever
supposed to make one sort faster.

Reproduced against real Postgres: with statement_timeout=1ms, ensure_sort_index
raised QueryCanceled and left idx_..._sort_quality_score with indisvalid=false.
"""

import logging

import pytest

from .common import get_meta_store


def test_a_cancelled_build_does_not_propagate_out_of_ensure_sort_index(monkeypatch):
    # The boot path must survive a build the server kills mid-flight.
    import psycopg2

    store = get_meta_store("postgres")

    real_connect = psycopg2.connect

    def timing_out_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '1ms'")
        return conn

    monkeypatch.setattr(psycopg2, "connect", timing_out_connect)

    store.ensure_sort_index("score")  # must not raise


def test_the_field_is_still_registered_when_the_build_fails(monkeypatch):
    # Registration follows the ANNOTATION, not the DDL outcome (#422): pods must
    # emit identical SQL whether or not their build won the race or failed.
    import psycopg2

    store = get_meta_store("postgres")

    real_connect = psycopg2.connect

    def timing_out_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '1ms'")
        return conn

    monkeypatch.setattr(psycopg2, "connect", timing_out_connect)

    store.ensure_sort_index("score")
    assert "score" in store._sort_indexes


def test_a_failed_build_is_logged_not_silently_swallowed(monkeypatch, caplog):
    # Degrading to "slow" is only acceptable if an operator can find out why.
    import psycopg2

    store = get_meta_store("postgres")

    real_connect = psycopg2.connect

    def timing_out_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '1ms'")
        return conn

    monkeypatch.setattr(psycopg2, "connect", timing_out_connect)

    with caplog.at_level(logging.WARNING):
        store.ensure_sort_index("score")
    assert any("score" in r.message for r in caplog.records), caplog.text


def test_a_connect_failure_does_not_propagate_either(monkeypatch):
    # The DDL opens its OWN connection (CONCURRENTLY cannot run in the pooled
    # transaction). If that connect fails, boot must still proceed.
    import psycopg2

    store = get_meta_store("postgres")

    def refusing_connect(*args, **kwargs):
        raise psycopg2.OperationalError("connection refused")

    monkeypatch.setattr(psycopg2, "connect", refusing_connect)

    store.ensure_sort_index("score")  # must not raise
    assert "score" in store._sort_indexes


@pytest.mark.parametrize("field", ["score"])
def test_a_successful_build_still_produces_a_valid_index(field: str):
    # The guard must not have turned the happy path into a silent no-op.
    store = get_meta_store("postgres")
    store.ensure_sort_index(field)
    idx = store._sort_idx_name(field)
    with store.transaction() as cur:
        cur.execute(
            "SELECT indisvalid FROM pg_index WHERE indexrelid = to_regclass(%s)", [idx]
        )
        row = cur.fetchone()
    assert row is not None and row[0] is True
