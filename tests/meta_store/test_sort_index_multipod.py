"""SortIndex when several pods boot at once — the normal case in production.

``ensure_sort_index`` runs from ``add_model``, i.e. on every process start, and
Postgres permits only ONE concurrent index build per table at a time. N pods
racing to ``CREATE INDEX CONCURRENTLY`` deadlock each other, which on Kubernetes
is a CrashLoopBackOff on the first rollout after the annotation ships — the worst
possible moment.

The escape is #418's own premise: an index's absence costs only speed, never
correctness. So a pod that loses the race can simply not build it. What it must
NOT do is behave differently: the emitted SQL is decided by the ANNOTATION, which
is identical code on every pod, and never by whether this pod won the race or the
DDL even succeeded. Otherwise pods disagree — and on a string field the two forms
do not merely differ in speed, one of them raises.
"""

import threading
import uuid

import pytest

from specstar.query import QB
from specstar.query_types import DataSearchCondition, DataSearchOperator
from specstar.resource_manager.meta_store.postgres import PostgresMetaStore
from specstar.types import ResourceMeta

DSN = "postgresql://admin:password@localhost:5432/your_database"
N_PODS = 6


def _meta(rid: str, score) -> ResourceMeta:
    from datetime import UTC, datetime

    base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    return ResourceMeta(
        current_revision_id=f"rev_{rid}",
        resource_id=f"id-{rid}",
        total_revision_count=1,
        created_time=base,
        updated_time=base,
        created_by="t",
        updated_by="t",
        is_deleted=False,
        indexed_data={"id": rid, "score": score},
    )


@pytest.fixture
def table():
    t = "multipod_" + uuid.uuid4().hex[:8]
    seed = PostgresMetaStore(pg_dsn=DSN, table_name=t)
    for i in range(400):
        seed[f"id-{i}"] = _meta(str(i), i)
    yield t
    with seed.transaction() as cur:
        cur.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE')


def _hits(store: PostgresMetaStore, cond) -> list[str]:
    out = []
    for m in store.iter_search(cond.build()):
        assert isinstance(m.indexed_data, dict)  # narrow dict | UnsetType for ty
        out.append(m.indexed_data["id"])
    return sorted(out)


def _boot_pods(table: str, n: int = N_PODS):
    """n pods calling ensure_sort_index simultaneously, as add_model does."""
    results: list = []

    def pod(i):
        try:
            s = PostgresMetaStore(pg_dsn=DSN, table_name=table)
            s.ensure_sort_index("score")
            results.append((i, "OK", _hits(s, QB["score"] > 396), s))
        except Exception as e:  # noqa: BLE001
            results.append((i, f"{type(e).__name__}: {e}", None, None))

    threads = [threading.Thread(target=pod, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def test_concurrent_boot_does_not_deadlock(table):
    """Postgres allows one concurrent build per table; N pods must not fight."""
    results = _boot_pods(table)
    failures = [(i, err) for i, err, _, _ in results if err != "OK"]
    assert not failures, f"pods crashed on boot: {failures}"


def test_every_pod_answers_identically_regardless_of_who_built_the_index(table):
    """The index lives in Postgres, not in the pod: whoever builds it, all pods
    see it. Until then they all seq-scan — slow, never wrong."""
    results = _boot_pods(table)
    answers = {tuple(hits) for _, err, hits, _ in results if err == "OK"}
    assert len(answers) == 1, f"pods disagreed: {answers}"
    assert answers.pop() == ("397", "398", "399")


def test_every_pod_emits_identical_sql(table):
    """The SQL form must follow the annotation, not the DDL outcome."""
    results = _boot_pods(table)
    cond = DataSearchCondition(
        field_path="score", operator=DataSearchOperator.greater_than, value=396
    )
    sqls = {s._build_condition(cond)[0] for _, err, _, s in results if err == "OK"}
    assert len(sqls) == 1, f"pods emitted different SQL: {sqls}"


def test_the_index_ends_up_valid_after_a_concurrent_boot(table):
    _boot_pods(table)
    s = PostgresMetaStore(pg_dsn=DSN, table_name=table)
    with s.transaction() as cur:
        cur.execute(
            "SELECT indisvalid FROM pg_index WHERE indexrelid = to_regclass(%s)",
            [s._sort_idx_name("score")],
        )
        row = cur.fetchone()
    assert row is not None and row[0], "no valid index after all pods booted"


def test_an_invalid_index_left_by_a_failed_build_is_repaired(table):
    """A build killed mid-flight (OOM, eviction) leaves an INVALID index behind.

    ``CREATE INDEX CONCURRENTLY IF NOT EXISTS`` then matches it BY NAME and skips
    forever, and the planner ignores invalid indexes — so the annotation would be
    silently dead for good.
    """
    s = PostgresMetaStore(pg_dsn=DSN, table_name=table)
    idx = s._sort_idx_name("score")

    # Force a failed build the way Postgres documents: a unique violation.
    # (psycopg2 raises UniqueViolation, a subclass — named by its stubbed parent.)
    import psycopg2

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(f'ALTER TABLE "{table}" ADD COLUMN dup int DEFAULT 1')
            with pytest.raises(psycopg2.IntegrityError):
                cur.execute(
                    f'CREATE UNIQUE INDEX CONCURRENTLY "{idx}" ON "{table}" (dup)'
                )
        with conn.cursor() as cur:
            cur.execute(
                "SELECT indisvalid FROM pg_index WHERE indexrelid = to_regclass(%s)",
                [idx],
            )
            assert cur.fetchone()[0] is False, (
                "expected an invalid index to squat on the name"
            )
    finally:
        conn.close()

    s.ensure_sort_index("score")

    with s.transaction() as cur:
        cur.execute(
            "SELECT indisvalid FROM pg_index WHERE indexrelid = to_regclass(%s)", [idx]
        )
        row = cur.fetchone()
    assert row is not None and row[0], "the invalid index was not repaired"


def test_results_are_correct_even_if_the_ddl_cannot_run(table, monkeypatch):
    """A pod that cannot build the index must still answer correctly.

    This is the whole premise: registration follows the annotation, the DDL is
    best effort.
    """
    s = PostgresMetaStore(pg_dsn=DSN, table_name=table)

    def boom(*a, **k):
        raise RuntimeError("simulated: DDL unavailable")

    monkeypatch.setattr(s, "_build_sort_index_ddl", boom, raising=False)
    try:
        s.ensure_sort_index("score")
    except RuntimeError:
        pass  # even if it propagates, registration must already have happened

    assert "score" in s._sort_indexes
    assert _hits(s, QB["score"] > 396) == ["397", "398", "399"]
