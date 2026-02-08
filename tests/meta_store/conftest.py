"""Pytest configuration for meta_store tests."""

import gc

import pytest


@pytest.fixture(autouse=True)
def cleanup_sqlalchemy_connections(request):
    """Cleanup SQLAlchemy connections after each test to prevent connection pool exhaustion."""
    yield

    # Force garbage collection to close any lingering connections
    gc.collect()

    # If test used a meta_store, dispose its engine
    if hasattr(request, "instance") and hasattr(request.instance, "meta_store"):
        meta_store = request.instance.meta_store
        if hasattr(meta_store, "_engine") and meta_store._engine:
            try:
                # Close all connections in the pool
                meta_store._engine.dispose()
            except Exception:
                pass  # Ignore disposal errors
