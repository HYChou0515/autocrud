import time
from uuid import uuid4
from autocrud.resource_manager.resource_store.cache import MemoryCache
from autocrud.types import RevisionInfo


def test_memory_cache_data_expiration():
    cache = MemoryCache()
    resource_id = "res1"
    revision_id = "rev1"
    schema_version = "v1"
    data = b"some data"

    # Set a very short TTL
    cache.put_data(resource_id, revision_id, schema_version, data, ttl=0.1)

    # Wait for expiration
    time.sleep(0.2)

    # This should trigger line 107-108: _is_expired is true, so delete from store and return None
    result = cache.get_data(resource_id, revision_id, schema_version)
    assert result is None

    # Verify it's gone from internal store (though get_data already did that)
    key = cache._get_key(resource_id, revision_id, schema_version)
    assert key not in cache._data_store


def test_memory_cache_info_expiration():
    cache = MemoryCache()
    info = RevisionInfo(
        uid=uuid4(),
        resource_id="res1",
        revision_id="rev1",
        schema_version="v1",
        created_by="user",
        created_time=None,  # type: ignore
        updated_by="user",
        updated_time=None,  # type: ignore
        status="draft",  # type: ignore
    )

    # Set a very short TTL
    cache.put_revision_info(info, ttl=0.1)

    # Wait for expiration
    time.sleep(0.2)

    # This should trigger expiration logic for revision info
    result = cache.get_revision_info(
        info.resource_id, info.revision_id, info.schema_version
    )
    assert result is None

    # Verify it's gone
    key = cache._get_key(info.resource_id, info.revision_id, info.schema_version)
    assert key not in cache._info_store
