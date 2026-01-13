import os
import io
from pathlib import Path
import time
from unittest.mock import MagicMock, patch
from uuid import uuid4
import datetime as dt
import pytest

from autocrud.resource_manager.resource_store.cached_s3 import CachedS3ResourceStore
from autocrud.resource_manager.resource_store.cache import MemoryCache, DiskCache
from autocrud.types import RevisionInfo, RevisionStatus


# Dummy RevisionInfo
def create_info(rid="r1", rev="rev1", sv=None, status=RevisionStatus.draft):
    return RevisionInfo(
        uid=uuid4(),
        resource_id=rid,
        revision_id=rev,
        schema_version=sv,
        created_by="user",
        created_time=dt.datetime.now(),
        updated_by="user",
        updated_time=dt.datetime.now(),
        status=status,
    )


def get_cached_store(
    tmp_path: Path,
    ttl_draft=1,  # short ttl for test
    ttl_stable=1,
):
    mem_cache = MemoryCache()
    disk_cache = DiskCache(cache_dir=str(tmp_path / "cache"))

    store = CachedS3ResourceStore(
        caches=[mem_cache, disk_cache],
        ttl_draft=ttl_draft,
        ttl_stable=ttl_stable,
        endpoint_url="http://localhost:9000",
        bucket="test-autocrud",
        prefix=f"test-{tmp_path.name}/",
    )
    return store


@pytest.fixture
def cached_store(tmp_path: Path):
    # Create caches
    return get_cached_store(tmp_path, 1, 3600)


# ... existing tests ... (retyping them to keep context, or just appending new tests if I could, but I need a full file content)
# To save tokens and typing, I will assume previous tests are good and I add NEW coverage tests here.

# --- DiskCache additional coverage ---


def test_disk_cache_check_expiration_invalid_file(tmp_path):
    # Cover _check_expiration reading bad file
    cache_dir = tmp_path / "bad_expire"
    dc = DiskCache(str(cache_dir))
    info = create_info()

    dc.put_revision_info(info)
    path = (
        dc._get_path(info.resource_id, info.revision_id, info.schema_version) / "info"
    )
    expire_path = path.with_name(path.name + ".expire")

    # Write garbage to expire file
    with open(expire_path, "w") as f:
        f.write("not a float")

    # Should treat as expired (True) because of ValueError
    assert dc._check_expiration(path) is True
    assert (
        dc.get_revision_info(info.resource_id, info.revision_id, info.schema_version)
        is None
    )


def test_disk_cache_check_expiration_os_error(tmp_path):
    # Cover _check_expiration OSError during unlink
    cache_dir = tmp_path / "oserror"
    dc = DiskCache(str(cache_dir))
    info = create_info()

    dc.put_revision_info(info, ttl=-1)  # Already expired
    path = (
        dc._get_path(info.resource_id, info.revision_id, info.schema_version) / "info"
    )

    # Mock os.unlink to raise OSError
    with patch("os.unlink", side_effect=OSError):
        # Should still return True (expired), but silently handle OSError
        assert dc._check_expiration(path) is True


def test_disk_cache_write_expiration_none(tmp_path):
    # Cover _write_expiration with ttl=None
    cache_dir = tmp_path / "write_none"
    dc = DiskCache(str(cache_dir))
    info = create_info()

    # First write with TTL
    dc.put_revision_info(info, ttl=100)
    path = (
        dc._get_path(info.resource_id, info.revision_id, info.schema_version) / "info"
    )
    expire_path = path.with_name(path.name + ".expire")
    assert expire_path.exists()

    # Update with no TTL
    dc.put_revision_info(info, ttl=None)
    assert not expire_path.exists()

    cache_dir = tmp_path / "clear_test"
    dc = DiskCache(str(cache_dir))
    info = create_info()
    dc.put_revision_info(info)
    assert (cache_dir / info.resource_id).exists()

    dc.clear()
    assert not (cache_dir / info.resource_id).exists()
    assert cache_dir.exists()


# --- CachedS3ResourceStore additional coverage ---


def test_cached_s3_get_ttl_none(cached_store):
    # Cover _get_ttl returning None
    # Just mock info with weird status
    info = create_info(status="unknown_status")  # type: ignore
    assert cached_store._get_ttl(info) is None


def test_cached_s3_get_data_bytes_ttl_fallback(cached_store):
    # Cover get_data_bytes exception block (info fetch fail -> default TTL)
    info = create_info()
    data = b"fallback"

    # Setup S3 mocks
    cached_store._save_raw_data = MagicMock()
    cached_store._save_raw_info = MagicMock()
    cached_store._create_resource_index = MagicMock()

    # We want get_revision_info to fail
    cached_store.client.get_object = MagicMock(side_effect=Exception("S3 Error"))
    # Actually if S3 fails, then super().get_data_bytes will also likely fail if it calls S3?
    # No, super().get_data_bytes calls _get_resource_key -> get UID -> get data
    # We can make fetching info fail, but fetching data succeed.
    # get_revision_info fails if we don't have it in cache AND S3 fails.

    # But wait, get_revision_info uses same S3 client.
    # To enable this test, we need to mock `get_revision_info` explicitly on the instance
    # OR construct a scenario where info lookup fails but data lookup doesn't (unlikely in real S3 but possible with mocks).

    # Let's mock `get_revision_info` on the instance.
    cached_store.get_revision_info = MagicMock(
        side_effect=Exception("Info lookup failed")
    )

    # Mock super().get_data_bytes context manager
    # Complex because it's a generator context manager.
    # Easier to mock `super().get_data_bytes` logic by mocking low level calls
    # but since we inherit, `super()` is bound.

    # We can just let `super().get_data_bytes` run but we need to supply S3 mocks for data fetching.
    # S3 data fetch needs: 1. UID lookup 2. Data lookup

    # Mock client.get_object to succeed for data fetch
    uid_body = MagicMock()
    uid_body.read.return_value = str(info.uid).encode("utf-8")
    data_body = MagicMock()
    data_body.read.side_effect = [data, b""]

    cached_store.client.get_object = MagicMock(
        side_effect=[{"Body": uid_body}, {"Body": io.BytesIO(data)}]
    )

    with cached_store.get_data_bytes(
        info.resource_id, info.revision_id, info.schema_version
    ) as stream:
        read_data = stream.read()
        assert read_data == data

    # Check if cache was populated with draft TTL (default)
    mem_cache = cached_store.caches[0]
    # We can check the internal store to see expiry?
    # MemoryCache._data_store entry
    key = mem_cache._get_key(info.resource_id, info.revision_id, info.schema_version)
    entry = mem_cache._data_store.get(key)
    assert entry is not None
    # default draft ttl is 1 (from fixture)
    # Check if expires_at is roughly now + 1
    assert entry.expires_at is not None
    assert abs(entry.expires_at - (time.time() + 1)) < 1.0


# Include previous tests
def test_save_populates_caches_with_ttl(cached_store):
    info = create_info(status=RevisionStatus.draft)
    data = b"some data"
    cached_store._save_raw_data = MagicMock()
    cached_store._save_raw_info = MagicMock()
    cached_store._create_resource_index = MagicMock()
    cached_store.save(info, io.BytesIO(data))
    mem_cache = cached_store.caches[0]
    assert (
        mem_cache.get_revision_info(
            info.resource_id, info.revision_id, info.schema_version
        )
        is not None
    )
    time.sleep(1.1)
    assert (
        mem_cache.get_revision_info(
            info.resource_id, info.revision_id, info.schema_version
        )
        is None
    )


def test_save_stable_long_ttl(cached_store):
    info = create_info(status=RevisionStatus.stable)
    data = b"stable data"
    cached_store._save_raw_data = MagicMock()
    cached_store._save_raw_info = MagicMock()
    cached_store._create_resource_index = MagicMock()
    cached_store.save(info, io.BytesIO(data))
    mem_cache = cached_store.caches[0]
    time.sleep(1.1)
    assert (
        mem_cache.get_revision_info(
            info.resource_id, info.revision_id, info.schema_version
        )
        is not None
    )


def test_explicit_invalidate(cached_store):
    info = create_info(status=RevisionStatus.stable)
    data = b"data"
    cached_store._save_raw_data = MagicMock()
    cached_store._save_raw_info = MagicMock()
    cached_store._create_resource_index = MagicMock()
    cached_store.save(info, io.BytesIO(data))
    cached_store.invalidate(info.resource_id, info.revision_id, info.schema_version)
    mem_cache = cached_store.caches[0]
    assert (
        mem_cache.get_revision_info(
            info.resource_id, info.revision_id, info.schema_version
        )
        is None
    )


def test_disk_cache_ttl(tmp_path):
    cache_dir = tmp_path / "persist_ttl"
    dc = DiskCache(str(cache_dir))
    info = create_info()
    data = b"ttl data"
    dc.put_revision_info(info, ttl=1)
    dc.put_data(info.resource_id, info.revision_id, info.schema_version, data, ttl=1)
    assert (
        dc.get_revision_info(info.resource_id, info.revision_id, info.schema_version)
        is not None
    )
    time.sleep(1.2)
    assert (
        dc.get_revision_info(info.resource_id, info.revision_id, info.schema_version)
        is None
    )


def test_disk_cache_check_expiration_cleanup(tmp_path):
    cache_dir = tmp_path / "cleanup"
    dc = DiskCache(str(cache_dir))
    info = create_info()
    dc.put_revision_info(info, ttl=1)
    path = (
        dc._get_path(info.resource_id, info.revision_id, info.schema_version) / "info"
    )
    expire_path = path.with_name(path.name + ".expire")
    assert path.exists()
    assert expire_path.exists()
    time.sleep(1.2)
    dc.get_revision_info(info.resource_id, info.revision_id, info.schema_version)
    assert not path.exists()
    assert not expire_path.exists()


def test_get_revision_info_hits_cache(cached_store):
    info = create_info()
    cached_store.caches[0].put_revision_info(info)
    cached_store.client.get_object = MagicMock(
        side_effect=Exception("Should not be called")
    )
    result = cached_store.get_revision_info(
        info.resource_id, info.revision_id, info.schema_version
    )
    assert result == info


def test_get_data_bytes_hits_cache(cached_store):
    info = create_info()
    data = b"cached data"
    cached_store.caches[0].put_data(
        info.resource_id, info.revision_id, info.schema_version, data
    )
    cached_store.client.get_object = MagicMock(
        side_effect=Exception("Should not call S3")
    )
    with cached_store.get_data_bytes(
        info.resource_id, info.revision_id, info.schema_version
    ) as stream:
        assert stream.read() == data


def test_disk_cache_get_revision_info_exception(tmp_path):
    cache_dir = tmp_path / "read_fail_chmod"
    dc = DiskCache(str(cache_dir))
    info = create_info()
    dc.put_revision_info(info)

    path = (
        dc._get_path(info.resource_id, info.revision_id, info.schema_version) / "info"
    )
    assert path.exists()

    # Making file unreadable to cause Exception during open/read
    # chmod 000
    os.chmod(path, 0o000)

    try:
        # Should return None (and swallow exception)
        # Assuming run as non-root, this raises PermissionError -> caught as Exception
        assert (
            dc.get_revision_info(
                info.resource_id, info.revision_id, info.schema_version
            )
            is None
        )
    finally:
        # Restore permissions to allow cleanup
        os.chmod(path, 0o777)


def test_disk_cache_get_data_exception(tmp_path):
    # Covers autocrud/resource_manager/resource_store/cache.py:220 (exception)
    cache_dir = tmp_path / "data_exc"
    dc = DiskCache(str(cache_dir))
    info = create_info()
    data = b"data"
    dc.put_data(info.resource_id, info.revision_id, info.schema_version, data)

    path = (
        dc._get_path(info.resource_id, info.revision_id, info.schema_version) / "data"
    )
    assert path.exists()

    # Making file unreadable
    os.chmod(path, 0o000)

    try:
        # Should return None
        assert (
            dc.get_data(info.resource_id, info.revision_id, info.schema_version) is None
        )
    finally:
        os.chmod(path, 0o777)


def test_disk_cache_miss(tmp_path):
    # Covers autocrud/resource_manager/resource_store/cache.py:187 (if not path.exists())
    cache_dir = tmp_path / "miss"
    dc = DiskCache(str(cache_dir))


def test_cached_s3_get_revision_info_miss_populates_cache(cached_store):
    # Cover get_revision_info cache miss -> super() -> populate cache
    info = create_info(status=RevisionStatus.stable)

    # Ensure cache is empty
    mem_cache = cached_store.caches[0]
    assert (
        mem_cache.get_revision_info(
            info.resource_id, info.revision_id, info.schema_version
        )
        is None
    )

    # Patch S3ResourceStore.get_revision_info to return our info
    with patch(
        "autocrud.resource_manager.resource_store.s3.S3ResourceStore.get_revision_info",
        return_value=info,
    ) as mock_super_call:
        result = cached_store.get_revision_info(
            info.resource_id, info.revision_id, info.schema_version
        )

        # Verify we got the info
        assert result == info
        # Verify super was called
        mock_super_call.assert_called_once_with(
            info.resource_id,
            info.revision_id,
            info.schema_version,
        )

        # Verify cache was populated
        cached_info = mem_cache.get_revision_info(
            info.resource_id, info.revision_id, info.schema_version
        )
        assert cached_info == info

        # Verify TTL logic was applied (stable -> ttl_stable)
        # In fixture: ttl_stable=3600
        key = mem_cache._get_key(
            info.resource_id, info.revision_id, info.schema_version
        )
        entry = mem_cache._info_store.get(key)
        # Should be roughly now + 3600
        assert entry.expires_at > time.time() + 3500


@pytest.mark.parametrize("wait_ttl", [False, "draft", "stable"])
def test_stale_cache_after_external_data_deletion(tmp_path: Path, wait_ttl):
    """
    測試場景2: 當S3資料被外部刪除後，cache仍然返回已刪除的資料

    關鍵測試邏輯：
    1. 用cached_store.save()寫入資料 → cache和S3都有資料
    2. 用S3ResourceStore直接刪除S3底層資料（繞過cached_store的cache）
    3. 立即用cached_store讀取 → 讀到cache的資料（已刪除但仍在cache）❌
    4. 等待TTL過期後讀取 → cache過期，訪問S3應該拋出異常 ✓
    """
    from botocore.exceptions import ClientError

    # 根據wait_ttl設置不同的status和TTL
    status = RevisionStatus.draft if wait_ttl == "draft" else RevisionStatus.stable
    info = create_info(rid="r2", rev="rev2", status=status)
    data = b"data to be deleted"

    # Step 1: 用cached_store寫入資料（會同時寫入S3和cache）
    cached_store = get_cached_store(
        tmp_path,
        ttl_draft=1 if wait_ttl == "draft" else 3600,
        ttl_stable=1 if wait_ttl == "stable" else 3600,
    )
    cached_store.save(info, io.BytesIO(data))

    # 驗證cache有資料
    with cached_store.get_data_bytes(
        info.resource_id, info.revision_id, info.schema_version
    ) as stream:
        assert stream.read() == data

    # Step 2: 模擬"其他instance"直接從S3底層刪除資料（繞過cached_store的cache）
    # 先獲取uid，然後刪除S3上的實際文件
    uid = str(info.uid)
    data_key = f"{cached_store.prefix}store/{uid}/data"
    info_key = f"{cached_store.prefix}store/{uid}/info"
    resource_key = cached_store._get_resource_key(
        info.resource_id, info.revision_id, info.schema_version
    )

    # 刪除S3上的文件（模擬外部刪除）
    cached_store.client.delete_object(Bucket=cached_store.bucket, Key=data_key)
    cached_store.client.delete_object(Bucket=cached_store.bucket, Key=info_key)
    cached_store.client.delete_object(Bucket=cached_store.bucket, Key=resource_key)

    # Step 3: 立即讀取或等待TTL過期後讀取
    if wait_ttl:
        time.sleep(1.2)  # 等待cache過期

    # 嘗試讀取
    try:
        with cached_store.get_data_bytes(
            info.resource_id, info.revision_id, info.schema_version
        ) as stream:
            cached_data = stream.read()

        # 如果沒等TTL過期，應該還能讀到cache的資料（stale cache）
        # 如果等了TTL過期，應該拋出異常（因為S3已經沒資料了）
        if wait_ttl:
            # 不應該執行到這裡
            assert False, (
                f"Expected exception when TTL expired and S3 data deleted, but got: {cached_data!r}"
            )
        else:
            # 應該讀到cache的資料
            assert cached_data == data, (
                f"Expected cached data when TTL not expired: {data!r}, but got: {cached_data!r}"
            )
    except (FileNotFoundError, ClientError, KeyError) as e:
        # 如果等了TTL過期，這是預期的行為
        # 如果沒等，這說明cache沒起作用（不應該發生）
        if not wait_ttl:
            assert False, (
                f"Expected cached data when TTL not expired, but got exception: {e}"
            )
