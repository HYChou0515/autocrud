"""Benchmark: backup (dump) & restore (load) with PostgreSQL + S3 storage.

Measures end-to-end throughput of AutoCRUD's ``.acbak`` archive export and
import using ``PostgreSQLStorageFactory`` (PostgreSQL meta + S3 resource/blob).

Requirements
~~~~~~~~~~~~
* PostgreSQL running (default: ``localhost:5432``)
* MinIO / S3 running (default: ``localhost:9000``)

Environment variables
~~~~~~~~~~~~~~~~~~~~~
* ``POSTGRES_DSN``  – PostgreSQL connection string
                     (default: ``postgresql://admin:password@localhost:5432/autocrud_bench``)
* ``S3_BUCKET``     – S3 bucket name (default: ``autocrud-bench``)
* ``S3_ENDPOINT_URL`` – MinIO endpoint (default: ``http://localhost:9000``)
* ``S3_ACCESS_KEY_ID`` / ``S3_SECRET_ACCESS_KEY`` – credentials (default: ``minioadmin``)

Run
~~~
::

    BENCHMARK=1 uv run pytest tests/test_benchmark_backup.py -v -s

Or via the Makefile::

    make test-benchmark
"""

from __future__ import annotations

import datetime as dt
import io
import os
import time
import uuid

import pytest
from msgspec import Struct

from autocrud.crud.core import AutoCRUD
from autocrud.resource_manager.basic import Encoding
from autocrud.types import Binary, OnDuplicate

# ---------------------------------------------------------------------------
# Skip unless benchmark mode is enabled
# ---------------------------------------------------------------------------

pytestmark = [
    pytest.mark.benchmark,
    pytest.mark.skipif(
        os.getenv("BENCHMARK") != "1",
        reason="Set BENCHMARK=1 to run backup benchmarks",
    ),
]

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

POSTGRES_DSN = os.getenv(
    "POSTGRES_DSN",
    "postgresql://admin:password@localhost:5432/autocrud_bench",
)
S3_BUCKET = os.getenv("S3_BUCKET", "autocrud-bench")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
S3_ACCESS_KEY_ID = os.getenv("S3_ACCESS_KEY_ID", "minioadmin")
S3_SECRET_ACCESS_KEY = os.getenv("S3_SECRET_ACCESS_KEY", "minioadmin")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "http://localhost:9000")

# Configurable sizes via env
SMALL_N = int(os.getenv("BENCH_SMALL_N", "100"))
LARGE_N = int(os.getenv("BENCH_LARGE_N", "1000"))
BLOB_N = int(os.getenv("BENCH_BLOB_N", "50"))
BLOB_SIZE = int(os.getenv("BENCH_BLOB_SIZE", str(64 * 1024)))  # 64 KB default


# ---------------------------------------------------------------------------
# Auto-provision: create database & S3 bucket if they don't exist
# ---------------------------------------------------------------------------


def _ensure_postgres_database():
    """Create the target database if it doesn't exist.

    Connects to the default ``postgres`` maintenance database, checks for
    the target DB, and issues ``CREATE DATABASE`` when missing.
    """
    try:
        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    except ImportError:
        return  # psycopg2 not installed — let the real test fail with a clear error

    from urllib.parse import urlparse

    parsed = urlparse(POSTGRES_DSN)
    db_name = parsed.path.lstrip("/")
    if not db_name:
        return

    # Connect to the default 'postgres' database
    maintenance_dsn = POSTGRES_DSN.rsplit("/", 1)[0] + "/postgres"
    try:
        conn = psycopg2.connect(maintenance_dsn)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{db_name}"')
            print(f"  [setup] Created PostgreSQL database: {db_name}")
        cur.close()
        conn.close()
    except Exception as exc:
        print(f"  [setup] Could not auto-create database: {exc}")


def _ensure_s3_bucket():
    """Create the target S3 bucket if it doesn't exist."""
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        return

    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=S3_ENDPOINT_URL,
            aws_access_key_id=S3_ACCESS_KEY_ID,
            aws_secret_access_key=S3_SECRET_ACCESS_KEY,
            region_name=S3_REGION,
        )
        try:
            s3.head_bucket(Bucket=S3_BUCKET)
        except ClientError:
            s3.create_bucket(Bucket=S3_BUCKET)
            print(f"  [setup] Created S3 bucket: {S3_BUCKET}")
    except Exception as exc:
        print(f"  [setup] Could not auto-create S3 bucket: {exc}")


# Run once at import time (only when BENCHMARK=1, otherwise the module is
# skipped entirely by the pytestmark above).
if os.getenv("BENCHMARK") == "1":
    _ensure_postgres_database()
    _ensure_s3_bucket()


# ---------------------------------------------------------------------------
# Test models
# ---------------------------------------------------------------------------


class Character(Struct):
    name: str
    level: int
    hp: int
    mp: int
    description: str = ""


class Equipment(Struct):
    name: str
    attack: int
    defense: int
    weight: float = 0.0


class Avatar(Struct):
    name: str
    image: Binary | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_storage_factory():
    """Build a PostgreSQLStorageFactory from environment variables."""
    from autocrud.resource_manager.storage_factory import PostgreSQLStorageFactory

    return PostgreSQLStorageFactory(
        connection_string=POSTGRES_DSN,
        s3_bucket=S3_BUCKET,
        s3_region=S3_REGION,
        s3_access_key_id=S3_ACCESS_KEY_ID,
        s3_secret_access_key=S3_SECRET_ACCESS_KEY,
        s3_endpoint_url=S3_ENDPOINT_URL,
        encoding=Encoding.msgpack,
        table_prefix="bench_backup_",
    )


def _make_crud(
    *models,
    storage_factory=None,
    indexed_fields=None,
) -> AutoCRUD:
    """Create an AutoCRUD instance backed by PostgreSQL + S3."""
    sf = storage_factory or _make_storage_factory()
    crud = AutoCRUD(storage_factory=sf)
    for m in models:
        crud.add_model(m, indexed_fields=indexed_fields or [])
    return crud


def _seed_characters(crud: AutoCRUD, n: int) -> list[str]:
    """Create *n* Character resources and return their IDs."""
    rm = crud.get_resource_manager(Character)
    ids = []
    with rm.meta_provide("bench", dt.datetime.now()):
        for i in range(n):
            meta = rm.create(
                Character(
                    name=f"hero_{i:05d}",
                    level=i % 100,
                    hp=100 + i,
                    mp=50 + i,
                    description=f"A brave hero number {i}. " * 5,
                )
            )
            ids.append(meta.resource_id)
    return ids


def _seed_equipment(crud: AutoCRUD, n: int) -> list[str]:
    """Create *n* Equipment resources and return their IDs."""
    rm = crud.get_resource_manager(Equipment)
    ids = []
    with rm.meta_provide("bench", dt.datetime.now()):
        for i in range(n):
            meta = rm.create(
                Equipment(
                    name=f"sword_{i:05d}",
                    attack=10 + i % 50,
                    defense=5 + i % 30,
                    weight=1.5 + (i % 20) * 0.1,
                )
            )
            ids.append(meta.resource_id)
    return ids


def _seed_avatars(crud: AutoCRUD, n: int, blob_size: int) -> list[str]:
    """Create *n* Avatar resources with random binary data."""
    rm = crud.get_resource_manager(Avatar)
    ids = []
    with rm.meta_provide("bench", dt.datetime.now()):
        for i in range(n):
            blob_data = os.urandom(blob_size)
            meta = rm.create(
                Avatar(
                    name=f"avatar_{i:04d}",
                    image=Binary(data=blob_data, content_type="image/png"),
                )
            )
            ids.append(meta.resource_id)
    return ids


def _dump_to_bytes(crud: AutoCRUD, **kw) -> bytes:
    buf = io.BytesIO()
    crud.dump(buf, **kw)
    return buf.getvalue()


def _load_from_bytes(crud: AutoCRUD, data: bytes, **kw):
    return crud.load(io.BytesIO(data), **kw)


def _format_size(nbytes: int) -> str:
    """Human-readable byte size."""
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


def _print_result(label: str, elapsed: float, archive_size: int, count: int):
    """Print formatted benchmark result."""
    rate = count / elapsed if elapsed > 0 else float("inf")
    throughput = archive_size / elapsed if elapsed > 0 else float("inf")
    print(
        f"  {label:30s}  "
        f"{elapsed:8.3f}s  "
        f"{rate:8.1f} rec/s  "
        f"{_format_size(int(throughput))}/s  "
        f"({_format_size(archive_size)} archive, {count} records)"
    )


# ======================================================================
# Benchmark tests
# ======================================================================


class TestBackupBenchmark:
    """End-to-end backup/restore benchmark with PostgreSQL + S3."""

    @pytest.fixture(autouse=True)
    def _unique_prefix(self, request):
        """Use a unique table/S3 prefix for each test run to avoid
        collisions with concurrent or repeated runs.  Cleans up
        PostgreSQL tables and S3 objects after the test finishes."""
        run_id = uuid.uuid4().hex[:8]
        self.storage_factory = _make_storage_factory()
        # Override table_prefix with a unique one
        self.storage_factory.table_prefix = f"bench_{run_id}_"
        # Track all table prefixes used (source + possible target)
        self._table_prefixes = [
            f"bench_{run_id}_",
            f"bench_{run_id}_tgt_",
        ]

        yield  # ── run the test ──

        # ── Cleanup: drop PG tables ──
        self._cleanup_pg_tables()
        # ── Cleanup: remove S3 objects ──
        self._cleanup_s3_objects()

    # ------------------------------------------------------------------
    # Cleanup helpers
    # ------------------------------------------------------------------

    def _cleanup_pg_tables(self):
        """Drop all PostgreSQL tables matching our benchmark prefixes."""
        try:
            import psycopg2
            from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
        except ImportError:
            return
        try:
            conn = psycopg2.connect(POSTGRES_DSN)
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cur = conn.cursor()
            for prefix in self._table_prefixes:
                cur.execute(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' AND tablename LIKE %s",
                    (f"{prefix}%",),
                )
                tables = [row[0] for row in cur.fetchall()]
                for table in tables:
                    cur.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
            cur.close()
            conn.close()
        except Exception as exc:
            print(f"  [cleanup] PG cleanup failed: {exc}")

    def _cleanup_s3_objects(self):
        """Remove all S3 objects created by the benchmark.

        Resource data lives under ``{model}/data/`` and blobs under
        ``blobs/``.  We clean all known model prefixes plus the blob
        prefix.
        """
        try:
            import boto3
        except ImportError:
            return
        try:
            s3 = boto3.client(
                "s3",
                endpoint_url=S3_ENDPOINT_URL,
                aws_access_key_id=S3_ACCESS_KEY_ID,
                aws_secret_access_key=S3_SECRET_ACCESS_KEY,
                region_name=S3_REGION,
            )
            # Model names are kebab-cased class names
            model_prefixes = ["character/data/", "equipment/data/", "avatar/data/"]
            all_prefixes = model_prefixes + ["blobs/"]
            for prefix in all_prefixes:
                self._delete_s3_prefix(s3, S3_BUCKET, prefix)
        except Exception as exc:
            print(f"  [cleanup] S3 cleanup failed: {exc}")

    @staticmethod
    def _delete_s3_prefix(s3_client, bucket: str, prefix: str):
        """Delete all objects under *prefix* in *bucket*."""
        paginator = s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            objects = page.get("Contents", [])
            if objects:
                keys = [{"Key": obj["Key"]} for obj in objects]
                s3_client.delete_objects(Bucket=bucket, Delete={"Objects": keys})

    # ------------------------------------------------------------------
    # Small dataset – metadata-only (no blobs)
    # ------------------------------------------------------------------

    def test_export_small(self):
        """Export {SMALL_N} Character resources."""
        crud = _make_crud(Character, storage_factory=self.storage_factory)
        ids = _seed_characters(crud, SMALL_N)
        print(f"\n--- Export {SMALL_N} characters (no blobs) ---")

        t0 = time.perf_counter()
        data = _dump_to_bytes(crud)
        elapsed = time.perf_counter() - t0

        _print_result("export", elapsed, len(data), len(ids))
        assert len(data) > 0

    def test_import_small(self):
        """Import {SMALL_N} Character resources into a fresh store."""
        # Phase 1: seed + export from source
        crud_src = _make_crud(Character, storage_factory=self.storage_factory)
        ids = _seed_characters(crud_src, SMALL_N)
        data = _dump_to_bytes(crud_src)
        print(f"\n--- Import {SMALL_N} characters (no blobs) ---")

        # Phase 2: import into fresh target
        target_factory = _make_storage_factory()
        target_factory.table_prefix = self.storage_factory.table_prefix + "tgt_"
        crud_tgt = _make_crud(Character, storage_factory=target_factory)

        t0 = time.perf_counter()
        stats = _load_from_bytes(crud_tgt, data)
        elapsed = time.perf_counter() - t0

        total_loaded = sum(s.loaded for s in stats.values())
        _print_result("import", elapsed, len(data), total_loaded)
        assert total_loaded == SMALL_N

    # ------------------------------------------------------------------
    # Large dataset – metadata-only (no blobs)
    # ------------------------------------------------------------------

    def test_export_large(self):
        """Export {LARGE_N} records across 2 models."""
        crud = _make_crud(Character, Equipment, storage_factory=self.storage_factory)
        n_char = LARGE_N // 2
        n_equip = LARGE_N - n_char
        ids_c = _seed_characters(crud, n_char)
        ids_e = _seed_equipment(crud, n_equip)
        total = len(ids_c) + len(ids_e)
        print(f"\n--- Export {total} records (2 models, no blobs) ---")

        t0 = time.perf_counter()
        data = _dump_to_bytes(crud)
        elapsed = time.perf_counter() - t0

        _print_result("export", elapsed, len(data), total)
        assert len(data) > 0

    def test_import_large(self):
        """Import {LARGE_N} records across 2 models."""
        crud_src = _make_crud(
            Character, Equipment, storage_factory=self.storage_factory
        )
        n_char = LARGE_N // 2
        n_equip = LARGE_N - n_char
        _seed_characters(crud_src, n_char)
        _seed_equipment(crud_src, n_equip)
        data = _dump_to_bytes(crud_src)
        total = n_char + n_equip
        print(f"\n--- Import {total} records (2 models, no blobs) ---")

        target_factory = _make_storage_factory()
        target_factory.table_prefix = self.storage_factory.table_prefix + "tgt_"
        crud_tgt = _make_crud(Character, Equipment, storage_factory=target_factory)

        t0 = time.perf_counter()
        stats = _load_from_bytes(crud_tgt, data)
        elapsed = time.perf_counter() - t0

        total_loaded = sum(s.loaded for s in stats.values())
        _print_result("import", elapsed, len(data), total_loaded)
        assert total_loaded == total

    # ------------------------------------------------------------------
    # Blob dataset – with binary attachments
    # ------------------------------------------------------------------

    def test_export_with_blobs(self):
        """Export {BLOB_N} Avatar resources with {BLOB_SIZE} byte blobs."""
        crud = _make_crud(Avatar, storage_factory=self.storage_factory)
        ids = _seed_avatars(crud, BLOB_N, BLOB_SIZE)
        total_blob_mb = (BLOB_N * BLOB_SIZE) / (1024 * 1024)
        print(
            f"\n--- Export {BLOB_N} avatars "
            f"(~{total_blob_mb:.1f} MB blob data, {_format_size(BLOB_SIZE)} each) ---"
        )

        t0 = time.perf_counter()
        data = _dump_to_bytes(crud)
        elapsed = time.perf_counter() - t0

        _print_result("export", elapsed, len(data), len(ids))
        assert len(data) > BLOB_N * BLOB_SIZE * 0.5  # sanity check

    def test_import_with_blobs(self):
        """Import {BLOB_N} Avatar resources with blobs."""
        crud_src = _make_crud(Avatar, storage_factory=self.storage_factory)
        ids = _seed_avatars(crud_src, BLOB_N, BLOB_SIZE)
        data = _dump_to_bytes(crud_src)
        total_blob_mb = (BLOB_N * BLOB_SIZE) / (1024 * 1024)
        print(
            f"\n--- Import {BLOB_N} avatars "
            f"(~{total_blob_mb:.1f} MB blob data, {_format_size(BLOB_SIZE)} each) ---"
        )

        target_factory = _make_storage_factory()
        target_factory.table_prefix = self.storage_factory.table_prefix + "tgt_"
        crud_tgt = _make_crud(Avatar, storage_factory=target_factory)

        t0 = time.perf_counter()
        stats = _load_from_bytes(crud_tgt, data)
        elapsed = time.perf_counter() - t0

        total_loaded = sum(s.loaded for s in stats.values())
        _print_result("import", elapsed, len(data), total_loaded)
        assert total_loaded == BLOB_N

    # ------------------------------------------------------------------
    # Roundtrip – export then import, verify correctness
    # ------------------------------------------------------------------

    def test_roundtrip_correctness(self):
        """Export → import → verify data integrity."""
        crud_src = _make_crud(
            Character, Equipment, storage_factory=self.storage_factory
        )
        _seed_characters(crud_src, min(SMALL_N, 50))
        _seed_equipment(crud_src, min(SMALL_N, 50))
        print("\n--- Roundtrip correctness check ---")

        data = _dump_to_bytes(crud_src)

        target_factory = _make_storage_factory()
        target_factory.table_prefix = self.storage_factory.table_prefix + "tgt_"
        crud_tgt = _make_crud(Character, Equipment, storage_factory=target_factory)
        stats = _load_from_bytes(crud_tgt, data)

        # Verify counts match
        for model_name, stat in stats.items():
            src_rm = crud_src.resource_managers[model_name]
            tgt_rm = crud_tgt.resource_managers[model_name]
            src_count = len(list(src_rm.iter_metas()))
            tgt_count = len(list(tgt_rm.iter_metas()))
            assert src_count == tgt_count, (
                f"{model_name}: source has {src_count} but target has {tgt_count}"
            )
            print(f"  {model_name}: {tgt_count} records verified ✓")

        # Verify data content for a sample
        src_rm = crud_src.get_resource_manager(Character)
        tgt_rm = crud_tgt.get_resource_manager(Character)
        for meta in list(src_rm.iter_metas())[:10]:
            src_data = src_rm.get(meta.resource_id)
            tgt_data = tgt_rm.get(meta.resource_id)
            assert src_data == tgt_data

    # ------------------------------------------------------------------
    # Import with on_duplicate=skip
    # ------------------------------------------------------------------

    def test_import_skip_duplicates(self):
        """Import over existing data with on_duplicate=skip."""
        crud = _make_crud(Character, storage_factory=self.storage_factory)
        _seed_characters(crud, SMALL_N)
        data = _dump_to_bytes(crud)
        print(f"\n--- Import {SMALL_N} characters (skip duplicates) ---")

        # Import again into the SAME store
        t0 = time.perf_counter()
        stats = _load_from_bytes(crud, data, on_duplicate=OnDuplicate.skip)
        elapsed = time.perf_counter() - t0

        total_skipped = sum(s.skipped for s in stats.values())
        _print_result("import (skip)", elapsed, len(data), SMALL_N)
        assert total_skipped == SMALL_N

    # ------------------------------------------------------------------
    # Import with on_duplicate=overwrite
    # ------------------------------------------------------------------

    def test_import_overwrite_duplicates(self):
        """Import over existing data with on_duplicate=overwrite."""
        crud = _make_crud(Character, storage_factory=self.storage_factory)
        _seed_characters(crud, SMALL_N)
        data = _dump_to_bytes(crud)
        print(f"\n--- Import {SMALL_N} characters (overwrite duplicates) ---")

        t0 = time.perf_counter()
        stats = _load_from_bytes(crud, data, on_duplicate=OnDuplicate.overwrite)
        elapsed = time.perf_counter() - t0

        total_loaded = sum(s.loaded for s in stats.values())
        _print_result("import (overwrite)", elapsed, len(data), total_loaded)
        assert total_loaded == SMALL_N
