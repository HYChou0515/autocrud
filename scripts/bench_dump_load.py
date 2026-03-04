"""Benchmark dump/load with PostgreSQL + S3 storage (MinIO).

Profiles per-phase timings and identifies bottlenecks in the PG+S3 path.

Requirements:
    - PostgreSQL running (default: localhost:5432)
    - MinIO / S3 running  (default: localhost:9000)

Usage:
    uv run python scripts/bench_dump_load.py [N]        # default N=1000
    uv run python scripts/bench_dump_load.py 5000
    uv run python scripts/bench_dump_load.py 1000 --profile
"""

from __future__ import annotations

import cProfile
import datetime as dt
import io
import os
import pstats
import sys
import time
import uuid

from msgspec import Struct

from autocrud.crud.core import AutoCRUD
from autocrud.resource_manager.basic import Encoding
from autocrud.types import OnDuplicate

# ---------------------------------------------------------------------------
# Configuration (override via env vars)
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


# ---------------------------------------------------------------------------
# Test model
# ---------------------------------------------------------------------------
class Item(Struct):
    name: str
    value: int
    description: str = ""
    tags: list[str] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_storage_factory(prefix: str = ""):
    from autocrud.resource_manager.storage_factory import PostgreSQLStorageFactory

    return PostgreSQLStorageFactory(
        connection_string=POSTGRES_DSN,
        s3_bucket=S3_BUCKET,
        s3_region=S3_REGION,
        s3_access_key_id=S3_ACCESS_KEY_ID,
        s3_secret_access_key=S3_SECRET_ACCESS_KEY,
        s3_endpoint_url=S3_ENDPOINT_URL,
        encoding=Encoding.msgpack,
        table_prefix=prefix,
    )


def make_crud(prefix: str = "") -> AutoCRUD:
    sf = _make_storage_factory(prefix)
    crud = AutoCRUD(storage_factory=sf)
    crud.add_model(Item)
    return crud


def make_memory_crud() -> AutoCRUD:
    crud = AutoCRUD()
    crud.add_model(Item)
    return crud


def seed(crud: AutoCRUD, n: int):
    mgr = crud.get_resource_manager(Item)
    with mgr.meta_provide("bench", dt.datetime(2025, 1, 1)):
        for i in range(n):
            mgr.create(
                Item(
                    name=f"item_{i:06d}",
                    value=i,
                    description=f"Description for item {i}. " * 3,
                    tags=[f"tag_{j}" for j in range(5)],
                )
            )


def _format_size(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


def _cleanup_pg_tables(prefix: str):
    """Drop all PG tables matching prefix."""
    try:
        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

        conn = psycopg2.connect(POSTGRES_DSN)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
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
        print(f"  [cleanup] PG: {exc}")


def _cleanup_s3_prefix(prefix: str):
    """Remove all S3 objects under prefix."""
    try:
        import boto3

        s3 = boto3.client(
            "s3",
            endpoint_url=S3_ENDPOINT_URL,
            aws_access_key_id=S3_ACCESS_KEY_ID,
            aws_secret_access_key=S3_SECRET_ACCESS_KEY,
            region_name=S3_REGION,
        )
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
            objects = page.get("Contents", [])
            if objects:
                keys = [{"Key": obj["Key"]} for obj in objects]
                s3.delete_objects(Bucket=S3_BUCKET, Delete={"Objects": keys})
    except Exception as exc:
        print(f"  [cleanup] S3: {exc}")


def _ensure_infra():
    """Create PG database and S3 bucket if they don't exist."""
    # PG database
    try:
        from urllib.parse import urlparse

        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

        parsed = urlparse(POSTGRES_DSN)
        db_name = parsed.path.lstrip("/")
        maintenance_dsn = POSTGRES_DSN.rsplit("/", 1)[0] + "/postgres"
        conn = psycopg2.connect(maintenance_dsn)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{db_name}"')
            print(f"  [setup] Created PG database: {db_name}")
        cur.close()
        conn.close()
    except Exception as exc:
        print(f"  [setup] PG: {exc}")

    # S3 bucket
    try:
        import boto3
        from botocore.exceptions import ClientError

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
        print(f"  [setup] S3: {exc}")


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------
def bench_dump(crud: AutoCRUD, label: str) -> bytes:
    buf = io.BytesIO()
    t0 = time.perf_counter()
    crud.dump(buf)
    elapsed = time.perf_counter() - t0
    data = buf.getvalue()
    rate = int(len(data) / elapsed) if elapsed > 0 else 0
    print(
        f"  DUMP {label}: {elapsed:.3f}s  "
        f"({_format_size(len(data))}, {_format_size(rate)}/s)"
    )
    return data


def bench_load(data: bytes, label: str, prefix: str) -> float:
    crud2 = make_crud(prefix)
    buf = io.BytesIO(data)
    t0 = time.perf_counter()
    stats = crud2.load(buf, on_duplicate=OnDuplicate.overwrite)
    elapsed = time.perf_counter() - t0
    total = sum(s.loaded for s in stats.values())
    rate = total / elapsed if elapsed > 0 else 0
    print(f"  LOAD {label}: {elapsed:.3f}s  ({total} records, {rate:.0f} rec/s)")
    return elapsed


def bench_load_memory(data: bytes, label: str) -> float:
    """Load into memory storage for comparison."""
    crud2 = make_memory_crud()
    buf = io.BytesIO(data)
    t0 = time.perf_counter()
    stats = crud2.load(buf, on_duplicate=OnDuplicate.overwrite)
    elapsed = time.perf_counter() - t0
    total = sum(s.loaded for s in stats.values())
    rate = total / elapsed if elapsed > 0 else 0
    print(
        f"  LOAD {label} (memory): {elapsed:.3f}s  ({total} records, {rate:.0f} rec/s)"
    )
    return elapsed


def profile_load(data: bytes, n: int, prefix: str):
    """Profile load with cProfile."""
    crud2 = make_crud(prefix)
    buf = io.BytesIO(data)
    pr = cProfile.Profile()
    pr.enable()
    crud2.load(buf, on_duplicate=OnDuplicate.overwrite)
    pr.disable()
    print(f"\n--- cProfile for LOAD {n} items PG+S3 (top 40) ---")
    ps = pstats.Stats(pr)
    ps.sort_stats("cumulative")
    ps.print_stats(40)


def profile_dump(crud: AutoCRUD, n: int):
    """Profile dump with cProfile."""
    buf = io.BytesIO()
    pr = cProfile.Profile()
    pr.enable()
    crud.dump(buf)
    pr.disable()
    print(f"\n--- cProfile for DUMP {n} items PG+S3 (top 40) ---")
    ps = pstats.Stats(pr)
    ps.sort_stats("cumulative")
    ps.print_stats(40)


def bench_load_breakdown(data: bytes, n: int, prefix: str):
    """Break down load into phases to show where time goes."""
    from autocrud.resource_manager.dump_format import (
        BlobRecord,
        DumpStreamReader,
        MetaRecord,
        RevisionRecord,
    )

    # Phase 1: Deserialize archive stream
    buf = io.BytesIO(data)
    t0 = time.perf_counter()
    reader = DumpStreamReader(buf)
    records = list(reader)
    t_deserialize = time.perf_counter() - t0

    meta_records = [r for r in records if isinstance(r, MetaRecord)]
    rev_records = [r for r in records if isinstance(r, RevisionRecord)]
    blob_records = [r for r in records if isinstance(r, BlobRecord)]
    print(f"\n  --- Load Breakdown for {n} items ---")
    print(
        f"  Records: {len(meta_records)} meta, {len(rev_records)} rev, "
        f"{len(blob_records)} blob"
    )
    print(f"  Phase 1 - Stream deserialize: {t_deserialize:.4f}s")

    # Phase 2: load_record per-type timing
    crud2 = make_crud(prefix)
    mgr = crud2.get_resource_manager(Item)

    # Time meta records
    t0 = time.perf_counter()
    for rec in meta_records:
        mgr.load_record(rec, OnDuplicate.overwrite)
    t_meta = time.perf_counter() - t0
    print(
        f"  Phase 2a - Load {len(meta_records)} MetaRecords: {t_meta:.4f}s  "
        f"({len(meta_records) / t_meta:.0f} rec/s)"
        if t_meta > 0
        else ""
    )

    # Time revision records
    t0 = time.perf_counter()
    for rec in rev_records:
        mgr.load_record(rec, OnDuplicate.overwrite)
    t_rev = time.perf_counter() - t0
    print(
        f"  Phase 2b - Load {len(rev_records)} RevisionRecords: {t_rev:.4f}s  "
        f"({len(rev_records) / t_rev:.0f} rec/s)"
        if t_rev > 0
        else ""
    )

    total = t_deserialize + t_meta + t_rev
    print(f"  TOTAL: {total:.4f}s")
    print(
        f"  Breakdown: deserialize={t_deserialize / total * 100:.1f}%, "
        f"meta={t_meta / total * 100:.1f}%, rev={t_rev / total * 100:.1f}%"
    )

    # Phase 3: Micro-breakdown of a single MetaRecord load
    # to see event-handler vs storage overhead
    if meta_records:
        rec = meta_records[0]
        import timeit

        # Decode only
        t_decode = (
            timeit.timeit(lambda: mgr.meta_serializer.decode(rec.data), number=1000)
            / 1000
        )
        print("\n  --- Per-record micro-timing (avg of 1000) ---")
        print(f"  MetaRecord decode: {t_decode * 1e6:.1f} µs")

        # Storage exists check
        meta_obj = mgr.meta_serializer.decode(rec.data)
        t_exists = (
            timeit.timeit(lambda: mgr.storage.exists(meta_obj.resource_id), number=1000)
            / 1000
        )
        print(f"  storage.exists(): {t_exists * 1e6:.1f} µs")

        # Storage save_meta
        t_save = (
            timeit.timeit(lambda: mgr.storage.save_meta(meta_obj), number=100) / 100
        )
        print(f"  storage.save_meta(): {t_save * 1e6:.1f} µs")

    if rev_records:
        rec = rev_records[0]
        raw_res = mgr.resource_serializer.decode(rec.data)

        t_decode = (
            timeit.timeit(lambda: mgr.resource_serializer.decode(rec.data), number=1000)
            / 1000
        )
        print(f"  RevisionRecord decode: {t_decode * 1e6:.1f} µs")

        t_save_rev = (
            timeit.timeit(
                lambda: mgr.storage.save_revision(
                    raw_res.info, io.BytesIO(raw_res.raw_data)
                ),
                number=100,
            )
            / 100
        )
        print(f"  storage.save_revision(): {t_save_rev * 1e6:.1f} µs")


def main():
    args = sys.argv[1:]
    do_profile = "--profile" in args
    args = [a for a in args if not a.startswith("--")]
    n = int(args[0]) if args else 1000

    _ensure_infra()
    run_id = uuid.uuid4().hex[:8]
    src_prefix = f"bench_{run_id}_src_"
    tgt_prefix = f"bench_{run_id}_tgt_"
    breakdown_prefix = f"bench_{run_id}_bd_"

    try:
        print(f"\n{'=' * 60}")
        print(f"  PG+S3 Dump/Load Benchmark  N={n}")
        print(f"  PG: {POSTGRES_DSN}")
        print(f"  S3: {S3_ENDPOINT_URL}/{S3_BUCKET}")
        print(f"  run_id: {run_id}")
        print(f"{'=' * 60}")

        # Seed into PG+S3
        crud = make_crud(src_prefix)
        t0 = time.perf_counter()
        seed(crud, n)
        print(f"\n  SEED ({n} items): {time.perf_counter() - t0:.3f}s")

        # Dump from PG+S3
        data = bench_dump(crud, f"{n} items from PG+S3")

        # Load into PG+S3
        bench_load(data, f"{n} items into PG+S3", tgt_prefix)

        # Load into memory (comparison)
        bench_load_memory(data, f"{n} items")

        # Breakdown
        bench_load_breakdown(data, n, breakdown_prefix)

        if do_profile:
            prof_prefix = f"bench_{run_id}_prof_"
            profile_dump(crud, n)
            profile_load(data, n, prof_prefix)
            _cleanup_pg_tables(prof_prefix)
            _cleanup_s3_prefix("item/data/")

    finally:
        # Cleanup
        print("\n  Cleaning up...")
        for p in [src_prefix, tgt_prefix, breakdown_prefix]:
            _cleanup_pg_tables(p)
        _cleanup_s3_prefix("item/data/")
        print("  Done.")


if __name__ == "__main__":
    main()
