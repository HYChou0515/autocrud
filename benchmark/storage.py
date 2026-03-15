"""Storage factory builders and availability checks.

Constructs the appropriate ``IStorageFactory`` from a
:class:`~benchmark.config.StorageConfig` and verifies that external
services (PostgreSQL, S3) are reachable.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from autocrud.resource_manager.basic import Encoding
from autocrud.resource_manager.storage_factory import (
    DiskStorageFactory,
    IStorageFactory,
    MemoryStorageFactory,
)


def build_storage_factory(
    storage_name: str,
    params: dict[str, Any],
    encoding: Encoding,
) -> IStorageFactory:
    """Create an ``IStorageFactory`` for the given backend.

    Args:
        storage_name: One of ``memory``, ``disk``, ``postgres``, ``s3``.
        params: Backend-specific parameters from the config.
        encoding: Serialization encoding (``json`` or ``msgpack``).

    Returns:
        An ``IStorageFactory`` instance ready to ``.build()`` per model.

    Raises:
        ValueError: If *storage_name* is not recognised.
    """
    if storage_name == "memory":
        return MemoryStorageFactory()

    if storage_name == "disk":
        rootdir = params.get("rootdir", "/tmp/autocrud-benchmark")
        return DiskStorageFactory(rootdir=rootdir)

    if storage_name == "postgres":
        from autocrud.resource_manager.storage_factory import PostgreSQLStorageFactory

        return PostgreSQLStorageFactory(
            connection_string=params["dsn"],
            s3_bucket=params["s3_bucket"],
            s3_endpoint_url=params.get("s3_endpoint_url"),
            s3_access_key_id=params.get("s3_access_key", "minioadmin"),
            s3_secret_access_key=params.get("s3_secret_key", "minioadmin"),
            encoding=encoding,
        )

    if storage_name == "s3":
        from autocrud.resource_manager.storage_factory import S3StorageFactory

        return S3StorageFactory(
            bucket=params["bucket"],
            endpoint_url=params.get("endpoint_url"),
            access_key_id=params.get("access_key", "minioadmin"),
            secret_access_key=params.get("secret_key", "minioadmin"),
            encoding=encoding,
        )

    raise ValueError(f"Unknown storage backend: {storage_name}")


def check_availability(storage_name: str, params: dict[str, Any]) -> tuple[bool, str]:
    """Check whether an external storage backend is reachable.

    Args:
        storage_name: Storage backend identifier.
        params: Backend parameters (connection strings, endpoints, …).

    Returns:
        ``(is_available, reason)`` — *reason* is empty when available.
    """
    if storage_name in ("memory", "disk"):
        return True, ""

    if storage_name == "postgres":
        dsn = params.get("dsn", "")
        if not dsn or "${" in dsn:
            return False, "POSTGRES_DSN not set"
        try:
            import psycopg2

            conn = psycopg2.connect(dsn, connect_timeout=3)
            conn.close()
            return True, ""
        except Exception as exc:
            return False, f"PostgreSQL unreachable: {exc}"

    if storage_name == "s3":
        bucket = params.get("bucket", "")
        endpoint = params.get("endpoint_url", "")
        if not bucket or "${" in bucket:
            return False, "S3_BUCKET not set"
        try:
            import boto3

            s3 = boto3.client(
                "s3",
                endpoint_url=endpoint or None,
                aws_access_key_id=params.get("access_key"),
                aws_secret_access_key=params.get("secret_key"),
            )
            s3.head_bucket(Bucket=bucket)
            return True, ""
        except Exception as exc:
            return False, f"S3 unreachable: {exc}"

    return False, f"Unknown storage: {storage_name}"


def cleanup_storage(storage_name: str, params: dict[str, Any]) -> None:
    """Remove artefacts left behind by a benchmark run.

    Args:
        storage_name: Storage backend identifier.
        params: Backend parameters.
    """
    if storage_name == "disk":
        rootdir = Path(params.get("rootdir", "/tmp/autocrud-benchmark"))
        if rootdir.exists():
            shutil.rmtree(rootdir, ignore_errors=True)

    elif storage_name == "postgres":
        _cleanup_postgres(params)

    elif storage_name == "s3":
        _cleanup_s3(params)


def _cleanup_postgres(params: dict[str, Any]) -> None:
    """Drop benchmark PostgreSQL tables and remove S3 data objects."""
    dsn = params.get("dsn", "")
    if not dsn or "${" in dsn:
        return

    # Drop benchmark meta tables
    try:
        import psycopg2

        conn = psycopg2.connect(dsn, connect_timeout=3)
        conn.autocommit = True
        cur = conn.cursor()
        # Find all *_meta tables created by the benchmark
        cur.execute(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename LIKE '%\\_meta'"
        )
        tables = [row[0] for row in cur.fetchall()]
        for table in tables:
            cur.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
        cur.close()
        conn.close()
    except Exception:
        pass

    # Clean S3 objects used by PostgreSQLStorageFactory
    bucket = params.get("s3_bucket", "")
    endpoint = params.get("s3_endpoint_url")
    if bucket and "${" not in bucket:
        _delete_all_s3_objects(
            bucket=bucket,
            endpoint_url=endpoint,
            access_key_id=params.get("s3_access_key", "minioadmin"),
            secret_access_key=params.get("s3_secret_key", "minioadmin"),
        )


def _cleanup_s3(params: dict[str, Any]) -> None:
    """Remove all objects in the benchmark S3 bucket."""
    bucket = params.get("bucket", "")
    endpoint = params.get("endpoint_url")
    if not bucket or "${" in bucket:
        return
    _delete_all_s3_objects(
        bucket=bucket,
        endpoint_url=endpoint,
        access_key_id=params.get("access_key", "minioadmin"),
        secret_access_key=params.get("secret_key", "minioadmin"),
    )


def _delete_all_s3_objects(
    *,
    bucket: str,
    endpoint_url: str | None,
    access_key_id: str,
    secret_access_key: str,
) -> None:
    """Delete every object in *bucket*."""
    try:
        import boto3

        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket):
            objects = page.get("Contents", [])
            if objects:
                s3.delete_objects(
                    Bucket=bucket,
                    Delete={"Objects": [{"Key": obj["Key"]} for obj in objects]},
                )
    except Exception:
        pass
