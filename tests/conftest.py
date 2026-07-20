"""Root pytest config.

Auto-applies ``@pytest.mark.integration`` to tests that require live
external services (Postgres, S3 / MinIO, real network) so that a fast
CI job can exclude them with ``-m "not integration and not benchmark
and not slow"``.

Adding the mark in one place keeps the per-file noise low. Add new
file patterns to ``INTEGRATION_FILE_PATTERNS`` as the suite grows.
"""

import fnmatch
from pathlib import Path

INTEGRATION_FILE_PATTERNS = (
    # Postgres-dependent
    "test_postgres_*.py",
    "test_postgresql_*.py",
    "test_postgres_disk_storage_factory.py",
    "test_storage_factory_kebab_table_name.py",
    "test_vector_integration.py",
    # S3 / MinIO dependent
    "test_advanced_cached_s3.py",
    "test_cached_s3.py",
    "test_s3_*.py",
    "test_blob_store_s3_*.py",
    # End-to-end wizard / wizard integration
    "test_wizard_integration.py",
    # Cross-backend resource store sweep (parametrizes over s3/cached_s3/pg)
    "test_resource_store.py",
    # Benchmarks pull in PG + S3
    "test_benchmark_backup.py",
    # Message queue brokers (RabbitMQ / Celery) — need a live broker
    "test_rabbitmq_*.py",
    "test_celery*.py",
)

INTEGRATION_SUBPATH_PREFIXES = (
    # The whole meta_store/ folder exercises live backends.
    "meta_store/",
)


def _is_integration_path(rel: str) -> bool:
    if any(rel.startswith(p) for p in INTEGRATION_SUBPATH_PREFIXES):
        return True
    name = Path(rel).name
    return any(fnmatch.fnmatch(name, pat) for pat in INTEGRATION_FILE_PATTERNS)


def pytest_collection_modifyitems(config, items):
    import pytest

    tests_root = Path(__file__).parent
    integration = pytest.mark.integration
    for item in items:
        try:
            rel = str(Path(item.fspath).relative_to(tests_root))
        except ValueError:
            continue
        if _is_integration_path(rel):
            item.add_marker(integration)
