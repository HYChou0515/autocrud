"""Tests for S3SqliteMetaStore using real S3/MinIO"""

import datetime as dt
import uuid

import pytest

from autocrud.resource_manager.basic import Encoding
from autocrud.resource_manager.meta_store.sqlite3 import S3SqliteMetaStore
from autocrud.types import ResourceMeta

# 使用真實的 S3/MinIO 連接進行測試
S3_ENDPOINT = "http://localhost:9000"
S3_BUCKET = "test-autocrud"
S3_ACCESS_KEY = "minioadmin"
S3_SECRET_KEY = "minioadmin"


@pytest.fixture
def s3_test_key():
    """生成唯一的測試 key 避免衝突"""
    return f"test-meta-store-{uuid.uuid4()}.db"


@pytest.fixture
def cleanup_s3_file():
    """測試後清理 S3 文件"""
    import boto3
    from botocore.exceptions import ClientError

    s3_client = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        region_name="us-east-1",
    )

    keys_to_cleanup = []

    yield keys_to_cleanup

    # 清理所有測試文件
    for key in keys_to_cleanup:
        try:
            s3_client.delete_object(Bucket=S3_BUCKET, Key=key)
        except ClientError:
            pass


def test_s3_sqlite_meta_store_initialization(s3_test_key, cleanup_s3_file):
    """測試 S3SqliteMetaStore 初始化"""
    cleanup_s3_file.append(s3_test_key)

    store = S3SqliteMetaStore(
        bucket=S3_BUCKET,
        key=s3_test_key,
        endpoint_url=S3_ENDPOINT,
        access_key_id=S3_ACCESS_KEY,
        secret_access_key=S3_SECRET_KEY,
        auto_sync=False,
    )

    assert store.bucket == S3_BUCKET
    assert store.key == s3_test_key
    assert store._db_filepath.exists()
    store.close()


def test_s3_sqlite_meta_store_basic_operations(s3_test_key, cleanup_s3_file):
    """測試基本的 CRUD 操作"""
    cleanup_s3_file.append(s3_test_key)

    store = S3SqliteMetaStore(
        bucket=S3_BUCKET,
        key=s3_test_key,
        endpoint_url=S3_ENDPOINT,
        access_key_id=S3_ACCESS_KEY,
        secret_access_key=S3_SECRET_KEY,
        auto_sync=False,
    )

    now = dt.datetime.now(dt.timezone.utc)

    # Create
    meta = ResourceMeta(
        current_revision_id="rev-001",
        resource_id="test-1",
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="user1",
        updated_by="user1",
        is_deleted=False,
        schema_version="1",
    )
    store["test-1"] = meta

    # Read
    retrieved = store["test-1"]
    assert retrieved.resource_id == "test-1"
    assert retrieved.current_revision_id == "rev-001"

    # Update
    meta.current_revision_id = "rev-002"
    store["test-1"] = meta
    assert store["test-1"].current_revision_id == "rev-002"

    # Delete
    del store["test-1"]
    assert "test-1" not in store

    store.close()


def test_s3_sqlite_meta_store_auto_sync(s3_test_key, cleanup_s3_file):
    """測試自動同步功能"""
    cleanup_s3_file.append(s3_test_key)

    store = S3SqliteMetaStore(
        bucket=S3_BUCKET,
        key=s3_test_key,
        endpoint_url=S3_ENDPOINT,
        access_key_id=S3_ACCESS_KEY,
        secret_access_key=S3_SECRET_KEY,
        auto_sync=True,
        sync_interval=0,  # 立即同步
    )

    now = dt.datetime.now(dt.timezone.utc)
    meta = ResourceMeta(
        current_revision_id="rev-001",
        resource_id="test-1",
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="user1",
        updated_by="user1",
        is_deleted=False,
        schema_version="1",
    )
    store["test-1"] = meta

    # 驗證文件已同步到 S3
    import boto3

    s3 = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        region_name="us-east-1",
    )

    response = s3.head_object(Bucket=S3_BUCKET, Key=s3_test_key)
    assert response["ETag"]  # 文件存在且有 ETag

    store.close()


def test_s3_sqlite_meta_store_manual_sync(s3_test_key, cleanup_s3_file):
    """測試手動同步"""
    cleanup_s3_file.append(s3_test_key)

    store = S3SqliteMetaStore(
        bucket=S3_BUCKET,
        key=s3_test_key,
        endpoint_url=S3_ENDPOINT,
        access_key_id=S3_ACCESS_KEY,
        secret_access_key=S3_SECRET_KEY,
        auto_sync=False,
    )

    now = dt.datetime.now(dt.timezone.utc)
    meta = ResourceMeta(
        current_revision_id="rev-001",
        resource_id="test-sync",
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="user",
        updated_by="user",
        is_deleted=False,
        schema_version="1",
    )
    store["test-sync"] = meta

    # 手動同步
    store.sync_to_s3()

    # 驗證文件已上傳
    import boto3

    s3 = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        region_name="us-east-1",
    )

    response = s3.head_object(Bucket=S3_BUCKET, Key=s3_test_key)
    assert response["ETag"]

    store.close()


def test_s3_sqlite_meta_store_etag_locking(s3_test_key, cleanup_s3_file):
    """測試 ETag 鎖定機制"""
    cleanup_s3_file.append(s3_test_key)

    from autocrud.resource_manager.meta_store.sqlite3 import S3ConflictError

    # 創建第一個實例並寫入數據
    store1 = S3SqliteMetaStore(
        bucket=S3_BUCKET,
        key=s3_test_key,
        endpoint_url=S3_ENDPOINT,
        access_key_id=S3_ACCESS_KEY,
        secret_access_key=S3_SECRET_KEY,
        auto_sync=False,
        enable_locking=True,
    )

    now = dt.datetime.now(dt.timezone.utc)
    meta = ResourceMeta(
        current_revision_id="rev-001",
        resource_id="test-1",
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="user1",
        updated_by="user1",
        is_deleted=False,
        schema_version="1",
    )
    store1["test-1"] = meta
    store1.sync_to_s3()
    etag1 = store1._current_etag

    # 創建第二個實例（從 S3 加載）
    store2 = S3SqliteMetaStore(
        bucket=S3_BUCKET,
        key=s3_test_key,
        endpoint_url=S3_ENDPOINT,
        access_key_id=S3_ACCESS_KEY,
        secret_access_key=S3_SECRET_KEY,
        auto_sync=False,
        enable_locking=True,
    )

    etag2 = store2._current_etag
    assert etag1 == etag2  # 兩個實例看到相同的 ETag

    # store1 修改並同步
    meta2 = ResourceMeta(
        current_revision_id="rev-002",
        resource_id="test-2",
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="user2",
        updated_by="user2",
        is_deleted=False,
        schema_version="1",
    )
    store1["test-2"] = meta2
    store1.sync_to_s3()

    # store2 嘗試同步應該失敗（ETag 不匹配）
    store2["test-3"] = meta
    with pytest.raises(S3ConflictError):
        store2.sync_to_s3()

    store1.close()
    store2.close()


def test_s3_sqlite_meta_store_check_etag_on_read(s3_test_key, cleanup_s3_file):
    """測試讀取時自動檢查 ETag 並重載"""
    cleanup_s3_file.append(s3_test_key)
    import time

    # 創建第一個實例並寫入數據
    store1 = S3SqliteMetaStore(
        bucket=S3_BUCKET,
        key=s3_test_key,
        endpoint_url=S3_ENDPOINT,
        access_key_id=S3_ACCESS_KEY,
        secret_access_key=S3_SECRET_KEY,
        auto_sync=True,
        sync_interval=0,
        enable_locking=True,
        check_etag_on_read=True,
    )

    now = dt.datetime.now(dt.timezone.utc)
    meta1 = ResourceMeta(
        current_revision_id="rev-001",
        resource_id="test-1",
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="user1",
        updated_by="user1",
        is_deleted=False,
        schema_version="1",
    )
    store1["test-1"] = meta1
    etag1 = store1._current_etag

    # 創建第二個實例
    store2 = S3SqliteMetaStore(
        bucket=S3_BUCKET,
        key=s3_test_key,
        endpoint_url=S3_ENDPOINT,
        access_key_id=S3_ACCESS_KEY,
        secret_access_key=S3_SECRET_KEY,
        auto_sync=True,
        sync_interval=0,
        enable_locking=True,
        check_etag_on_read=True,
    )

    assert store2._current_etag == etag1
    assert len(store2) == 1

    # store1 添加新數據
    meta2 = ResourceMeta(
        current_revision_id="rev-002",
        resource_id="test-2",
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="user2",
        updated_by="user2",
        is_deleted=False,
        schema_version="1",
    )
    store1["test-2"] = meta2

    # 等待超過檢查間隔
    time.sleep(1.1)

    # store2 讀取時應該自動重載並看到新數據
    resources = list(store2)
    assert len(resources) == 2
    assert store2._current_etag != etag1  # ETag 已更新

    store1.close()
    store2.close()


def test_s3_sqlite_meta_store_save_many(s3_test_key, cleanup_s3_file):
    """測試批量保存"""
    cleanup_s3_file.append(s3_test_key)

    store = S3SqliteMetaStore(
        bucket=S3_BUCKET,
        key=s3_test_key,
        endpoint_url=S3_ENDPOINT,
        access_key_id=S3_ACCESS_KEY,
        secret_access_key=S3_SECRET_KEY,
        auto_sync=True,
        sync_interval=0,
    )

    now = dt.datetime.now(dt.timezone.utc)
    metas = [
        ResourceMeta(
            current_revision_id=f"rev-{i:03d}",
            resource_id=f"test-{i}",
            total_revision_count=1,
            created_time=now,
            updated_time=now,
            created_by=f"user{i}",
            updated_by=f"user{i}",
            is_deleted=False,
            schema_version="1",
        )
        for i in range(5)
    ]

    store.save_many(metas)

    # 驗證所有數據都已保存
    assert len(store) == 5

    store.close()


def test_s3_sqlite_meta_store_search(s3_test_key, cleanup_s3_file):
    """測試搜索功能"""
    cleanup_s3_file.append(s3_test_key)
    from autocrud.types import ResourceMetaSearchQuery

    store = S3SqliteMetaStore(
        bucket=S3_BUCKET,
        key=s3_test_key,
        endpoint_url=S3_ENDPOINT,
        access_key_id=S3_ACCESS_KEY,
        secret_access_key=S3_SECRET_KEY,
        auto_sync=False,
    )

    now = dt.datetime.now(dt.timezone.utc)

    # 添加多個資源
    for i in range(5):
        meta = ResourceMeta(
            current_revision_id=f"rev-{i:03d}",
            resource_id=f"resource-{i}",
            total_revision_count=1,
            created_time=now,
            updated_time=now,
            created_by=f"user{i % 2}",  # user0 or user1
            updated_by=f"user{i % 2}",
            is_deleted=i >= 3,  # Last 2 are deleted
            schema_version="1",
        )
        store[f"resource-{i}"] = meta

    # 搜索未刪除的資源
    query = ResourceMetaSearchQuery(is_deleted=False)
    results = list(store.iter_search(query))
    assert len(results) == 3

    store.close()


def test_s3_sqlite_meta_store_force_sync(s3_test_key, cleanup_s3_file):
    """測試強制同步（繞過 ETag 檢查）"""
    cleanup_s3_file.append(s3_test_key)

    store = S3SqliteMetaStore(
        bucket=S3_BUCKET,
        key=s3_test_key,
        endpoint_url=S3_ENDPOINT,
        access_key_id=S3_ACCESS_KEY,
        secret_access_key=S3_SECRET_KEY,
        auto_sync=False,
        enable_locking=True,
    )

    now = dt.datetime.now(dt.timezone.utc)
    meta = ResourceMeta(
        current_revision_id="rev-001",
        resource_id="test-1",
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="user1",
        updated_by="user1",
        is_deleted=False,
        schema_version="1",
    )
    store["test-1"] = meta
    store.sync_to_s3()

    # 手動修改 ETag 模擬衝突
    old_etag = store._current_etag
    store._current_etag = '"fake-etag"'

    # 添加新數據
    meta2 = ResourceMeta(
        current_revision_id="rev-002",
        resource_id="test-2",
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="user2",
        updated_by="user2",
        is_deleted=False,
        schema_version="1",
    )
    store["test-2"] = meta2

    # 強制同步應該成功（繞過 ETag 檢查）
    store.sync_to_s3(force=True)

    # ETag 應該已更新
    assert store._current_etag != '"fake-etag"'
    # 因為數據有變化，ETag 也應該不同
    assert len(store) == 2

    store.close()


def test_s3_sqlite_meta_store_auto_reload_on_conflict(s3_test_key, cleanup_s3_file):
    """測試衝突時自動重載"""
    cleanup_s3_file.append(s3_test_key)
    from autocrud.resource_manager.meta_store.sqlite3 import S3ConflictError

    # 創建第一個實例
    store1 = S3SqliteMetaStore(
        bucket=S3_BUCKET,
        key=s3_test_key,
        endpoint_url=S3_ENDPOINT,
        access_key_id=S3_ACCESS_KEY,
        secret_access_key=S3_SECRET_KEY,
        auto_sync=False,
        enable_locking=True,
        auto_reload_on_conflict=False,
    )

    now = dt.datetime.now(dt.timezone.utc)
    meta1 = ResourceMeta(
        current_revision_id="rev-001",
        resource_id="test-1",
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="user1",
        updated_by="user1",
        is_deleted=False,
        schema_version="1",
    )
    store1["test-1"] = meta1
    store1.sync_to_s3()

    # 創建第二個實例，啟用自動重載
    store2 = S3SqliteMetaStore(
        bucket=S3_BUCKET,
        key=s3_test_key,
        endpoint_url=S3_ENDPOINT,
        access_key_id=S3_ACCESS_KEY,
        secret_access_key=S3_SECRET_KEY,
        auto_sync=False,
        enable_locking=True,
        auto_reload_on_conflict=True,
    )

    # store1 修改並同步
    meta2 = ResourceMeta(
        current_revision_id="rev-002",
        resource_id="test-2",
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="user2",
        updated_by="user2",
        is_deleted=False,
        schema_version="1",
    )
    store1["test-2"] = meta2
    store1.sync_to_s3()

    # store2 嘗試同步應該自動重載並報錯
    store2["test-3"] = meta1
    with pytest.raises(S3ConflictError):
        store2.sync_to_s3()

    # 但 store2 應該已經重載了 store1 的更改
    assert "test-2" in store2

    store1.close()
    store2.close()


def test_s3_sqlite_meta_store_encodings(s3_test_key, cleanup_s3_file):
    """測試不同編碼格式"""
    cleanup_s3_file.append(s3_test_key)

    for encoding in [Encoding.json, Encoding.msgpack]:
        store = S3SqliteMetaStore(
            bucket=S3_BUCKET,
            key=f"{encoding.name}-{s3_test_key}",
            endpoint_url=S3_ENDPOINT,
            access_key_id=S3_ACCESS_KEY,
            secret_access_key=S3_SECRET_KEY,
            encoding=encoding,
            auto_sync=False,
        )
        cleanup_s3_file.append(f"{encoding.name}-{s3_test_key}")

        now = dt.datetime.now(dt.timezone.utc)
        meta = ResourceMeta(
            current_revision_id="rev-001",
            resource_id="test-1",
            total_revision_count=1,
            created_time=now,
            updated_time=now,
            created_by="user",
            updated_by="user",
            is_deleted=False,
            schema_version="1",
        )
        store["test-1"] = meta

        # 驗證可以讀取
        retrieved = store["test-1"]
        assert retrieved.resource_id == "test-1"

        store.close()


def test_s3_sqlite_meta_store_locking_disabled(s3_test_key, cleanup_s3_file):
    """測試禁用鎖定功能"""
    cleanup_s3_file.append(s3_test_key)

    store = S3SqliteMetaStore(
        bucket=S3_BUCKET,
        key=s3_test_key,
        endpoint_url=S3_ENDPOINT,
        access_key_id=S3_ACCESS_KEY,
        secret_access_key=S3_SECRET_KEY,
        auto_sync=False,
        enable_locking=False,  # 禁用鎖定
    )

    now = dt.datetime.now(dt.timezone.utc)
    meta = ResourceMeta(
        current_revision_id="rev-001",
        resource_id="test-1",
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="user",
        updated_by="user",
        is_deleted=False,
        schema_version="1",
    )
    store["test-1"] = meta

    # 即使手動修改 ETag，同步也應該成功（因為禁用了鎖定）
    store._current_etag = '"fake-etag"'
    store.sync_to_s3()  # 不應該拋出異常

    store.close()


def test_s3_sqlite_meta_store_time_based_sync_interval(s3_test_key, cleanup_s3_file):
    """測試時間間隔同步 (674-676: elif branch)"""
    cleanup_s3_file.append(s3_test_key)
    import time

    store = S3SqliteMetaStore(
        bucket=S3_BUCKET,
        key=s3_test_key,
        endpoint_url=S3_ENDPOINT,
        access_key_id=S3_ACCESS_KEY,
        secret_access_key=S3_SECRET_KEY,
        auto_sync=True,
        sync_interval=0.5,  # 0.5秒間隔
        enable_locking=False,
    )

    now = dt.datetime.now(dt.timezone.utc)

    # 第一次寫入，還未到間隔時間
    meta1 = ResourceMeta(
        current_revision_id="rev-001",
        resource_id="test-1",
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="user1",
        updated_by="user1",
        is_deleted=False,
        schema_version="1",
    )
    store["test-1"] = meta1

    # 立即再寫入，不應該觸發同步
    first_sync_time = store._last_sync_time

    # 等待超過間隔時間
    time.sleep(0.6)

    # 再次寫入，應該觸發同步
    meta2 = ResourceMeta(
        current_revision_id="rev-002",
        resource_id="test-2",
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="user2",
        updated_by="user2",
        is_deleted=False,
        schema_version="1",
    )
    store["test-2"] = meta2

    # 驗證同步時間已更新
    assert store._last_sync_time > first_sync_time

    store.close()


def test_s3_sqlite_meta_store_del_cleanup(s3_test_key, cleanup_s3_file):
    """測試 __del__ 方法的清理 (830-837)"""
    cleanup_s3_file.append(s3_test_key)

    store = S3SqliteMetaStore(
        bucket=S3_BUCKET,
        key=s3_test_key,
        endpoint_url=S3_ENDPOINT,
        access_key_id=S3_ACCESS_KEY,
        secret_access_key=S3_SECRET_KEY,
        auto_sync=False,
        enable_locking=False,
    )

    now = dt.datetime.now(dt.timezone.utc)
    meta = ResourceMeta(
        current_revision_id="rev-001",
        resource_id="test-1",
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="user",
        updated_by="user",
        is_deleted=False,
        schema_version="1",
    )
    store["test-1"] = meta

    db_filepath = store._db_filepath

    # 通過 __del__ 清理
    del store

    # 驗證本地文件已被刪除
    assert not db_filepath.exists()


def test_s3_sqlite_meta_store_reload_with_s3_file_deleted(s3_test_key, cleanup_s3_file):
    """測試從 S3 重載時文件已被刪除的情況 (803-823)"""
    cleanup_s3_file.append(s3_test_key)
    import boto3

    # 創建並同步
    store = S3SqliteMetaStore(
        bucket=S3_BUCKET,
        key=s3_test_key,
        endpoint_url=S3_ENDPOINT,
        access_key_id=S3_ACCESS_KEY,
        secret_access_key=S3_SECRET_KEY,
        auto_sync=True,
        sync_interval=0,
        enable_locking=False,
    )

    now = dt.datetime.now(dt.timezone.utc)
    meta = ResourceMeta(
        current_revision_id="rev-001",
        resource_id="test-1",
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="user",
        updated_by="user",
        is_deleted=False,
        schema_version="1",
    )
    store["test-1"] = meta

    # 手動刪除 S3 文件
    s3 = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        region_name="us-east-1",
    )
    s3.delete_object(Bucket=S3_BUCKET, Key=s3_test_key)

    # 觸發重載（文件已不存在）
    store._reload_from_s3()

    # 應該創建空數據庫並初始化schema
    assert store._current_etag is None
    assert len(store) == 0  # 空數據庫

    # 應該能夠正常寫入
    meta2 = ResourceMeta(
        current_revision_id="rev-002",
        resource_id="test-2",
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="user",
        updated_by="user",
        is_deleted=False,
        schema_version="1",
    )
    store["test-2"] = meta2
    assert len(store) == 1

    store.close()


def test_s3_sqlite_meta_store_check_etag_s3_file_deleted(s3_test_key, cleanup_s3_file):
    """測試讀取檢查時 S3 文件已被刪除 (649->exit and 654-656)"""
    cleanup_s3_file.append(s3_test_key)
    import boto3
    import time

    # 創建並同步
    store = S3SqliteMetaStore(
        bucket=S3_BUCKET,
        key=s3_test_key,
        endpoint_url=S3_ENDPOINT,
        access_key_id=S3_ACCESS_KEY,
        secret_access_key=S3_SECRET_KEY,
        auto_sync=True,
        sync_interval=0,
        enable_locking=False,
        check_etag_on_read=True,
    )

    now = dt.datetime.now(dt.timezone.utc)
    meta = ResourceMeta(
        current_revision_id="rev-001",
        resource_id="test-1",
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="user",
        updated_by="user",
        is_deleted=False,
        schema_version="1",
    )
    store["test-1"] = meta

    # 測試快速連續讀取（間隔未到，應該走 649->exit 分支）
    resources1 = list(store)  # 第一次讀取
    assert len(resources1) == 1

    # 立即再次讀取（不到1秒間隔，應該跳過檢查）
    resources2 = list(store)  # 第二次讀取，應該不觸發ETag檢查
    assert len(resources2) == 1

    # 等待超過檢查間隔
    time.sleep(1.1)

    # 手動刪除 S3 文件
    s3 = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        region_name="us-east-1",
    )
    s3.delete_object(Bucket=S3_BUCKET, Key=s3_test_key)

    # 讀取時檢查 ETag，應該不會崩潰（檔案不存在時靜默處理）
    resources = list(store)  # 應該返回本地緩存的數據
    assert len(resources) == 1  # 本地仍有數據

    store.close()


def test_s3_sqlite_meta_store_check_etag_other_error(s3_test_key, cleanup_s3_file):
    """測試讀取檢查時遇到其他 S3 錯誤 (658-659: else branch)"""
    cleanup_s3_file.append(s3_test_key)
    import time
    from unittest.mock import patch
    from botocore.exceptions import ClientError

    # 創建並同步
    store = S3SqliteMetaStore(
        bucket=S3_BUCKET,
        key=s3_test_key,
        endpoint_url=S3_ENDPOINT,
        access_key_id=S3_ACCESS_KEY,
        secret_access_key=S3_SECRET_KEY,
        auto_sync=True,
        sync_interval=0,
        enable_locking=True,
        check_etag_on_read=True,
    )

    now = dt.datetime.now(dt.timezone.utc)
    meta = ResourceMeta(
        current_revision_id="rev-001",
        resource_id="test-1",
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="user",
        updated_by="user",
        is_deleted=False,
        schema_version="1",
    )
    store["test-1"] = meta

    # 等待超過檢查間隔
    time.sleep(1.1)

    # Mock head_object 拋出其他類型的錯誤
    def mock_head_object(*args, **kwargs):
        # 模擬權限錯誤
        error = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
            "HeadObject",
        )
        raise error

    with patch.object(store.s3_client, "head_object", side_effect=mock_head_object):
        # 讀取時檢查 ETag，遇到其他錯誤應該靜默忽略
        resources = list(store)  # 應該返回本地緩存的數據
        assert len(resources) == 1  # 本地仍有數據

    store.close()
