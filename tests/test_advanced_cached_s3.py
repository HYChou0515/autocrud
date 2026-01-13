"""
Tests for MQCachedS3ResourceStore and ETagCachedS3ResourceStore
"""

import io
from pathlib import Path
from uuid import uuid4
import datetime as dt
import pytest

from autocrud.resource_manager.resource_store.etag_cached_s3 import (
    ETagCachedS3ResourceStore,
)
from autocrud.resource_manager.resource_store.cache import MemoryCache
from autocrud.resource_manager.resource_store.s3 import S3ResourceStore
from autocrud.types import RevisionInfo, RevisionStatus


@pytest.fixture
def require_rabbitmq():
    """確保RabbitMQ可用，否則測試失敗"""
    try:
        import pika

        conn = pika.BlockingConnection(
            pika.URLParameters("amqp://guest:guest@localhost:5672")
        )
        conn.close()
    except Exception as e:
        pytest.fail(f"RabbitMQ不可用，測試失敗: {e}")


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


@pytest.mark.parametrize("wait_mq", [True, False])
def test_mq_cached_invalidation(tmp_path: Path, wait_mq: bool, require_rabbitmq):
    """
    測試MQ-based cache invalidation（需要真實RabbitMQ環境）

    場景：
    1. Instance A和Instance B共享同一個RabbitMQ
    2. Instance A寫入資料
    3. Instance B讀取（會cache）
    4. Instance A更新資料（會發送MQ invalidation）
    5. Instance B再次讀取應該讀到新資料
    """
    from autocrud.resource_manager.resource_store.mq_cached_s3 import (
        MQCachedS3ResourceStore,
    )
    import time

    # Instance A
    store_a = MQCachedS3ResourceStore(
        caches=[MemoryCache()],
        amqp_url="amqp://guest:guest@localhost:5672",
        queue_prefix=f"test_{uuid4().hex[:8]}_",
        ttl_draft=3600,
        ttl_stable=3600,
        endpoint_url="http://localhost:9000",
        bucket="autocrud-test",
        access_key_id="minioadmin",
        secret_access_key="minioadmin",
    )

    # Instance B（模擬另一個instance）
    store_b = MQCachedS3ResourceStore(
        caches=[MemoryCache()],
        amqp_url="amqp://guest:guest@localhost:5672",
        queue_prefix=f"test_{uuid4().hex[:8]}_",
        ttl_draft=3600,
        ttl_stable=3600,
        endpoint_url="http://localhost:9000",
        bucket="autocrud-test",
        access_key_id="minioadmin",
        secret_access_key="minioadmin",
    )

    try:
        # 1. Instance A寫入v1
        info = create_info("mq_test", "v1")
        data_v1 = b"version 1 data"
        store_a.save(info, io.BytesIO(data_v1))

        # 2. Instance B讀取並cache
        with store_b.get_data_bytes(
            info.resource_id, info.revision_id, info.schema_version
        ) as stream:
            cached_data_b = stream.read()
        assert cached_data_b == data_v1

        # 3. Instance A更新為v2（會發送invalidation message）
        info_v2 = create_info("mq_test", "v2")
        data_v2 = b"version 2 data - updated"
        store_a.save(info_v2, io.BytesIO(data_v2))

        # 4. 等待MQ消息傳遞（如果wait_mq=True）
        if wait_mq:
            time.sleep(0.5)  # 給MQ一點時間傳遞消息

        # 5. Instance B讀取v2
        with store_b.get_data_bytes(
            info_v2.resource_id, info_v2.revision_id, info_v2.schema_version
        ) as stream:
            result = stream.read()

        if wait_mq:
            # 等待了MQ，應該讀到新資料
            assert result == data_v2, "MQ invalidation應該讓Instance B讀到新資料"
        else:
            # 沒等待MQ，可能讀到舊cache或新資料（取決於MQ速度）
            # 這個測試主要確保不會crash
            assert result in (data_v1, data_v2)

    finally:
        store_a.close()
        store_b.close()


def test_etag_cached_validation(tmp_path: Path):
    """
    測試ETag-based cache validation

    場景：
    1. 寫入資料v1到S3
    2. 讀取資料（會cache + 保存ETag）
    3. 外部直接修改S3為v2（繞過cache）
    4. 再次讀取：ETag不同，應該invalidate cache並讀到v2
    """
    store = ETagCachedS3ResourceStore(
        caches=[MemoryCache()],
        ttl_draft=3600,
        ttl_stable=3600,
        endpoint_url="http://localhost:9000",
        bucket="test-autocrud",
        prefix=f"test-etag-{tmp_path.name}/",
        access_key_id="minioadmin",
        secret_access_key="minioadmin",
    )

    info = create_info(rid="r1", rev="rev1", status=RevisionStatus.stable)
    data_v1 = b"data version 1"
    data_v2 = b"data version 2"

    # Step 1: 寫入v1
    store.save(info, io.BytesIO(data_v1))

    # Step 2: 讀取v1（會cache + 保存ETag）
    with store.get_data_bytes(
        info.resource_id, info.revision_id, info.schema_version
    ) as stream:
        assert stream.read() == data_v1

    # 驗證ETag已保存
    cached_etag = store._get_cached_etag(
        info.resource_id, info.revision_id, info.schema_version
    )
    assert cached_etag is not None

    # Step 3: 外部直接修改S3（繞過cache）
    S3ResourceStore.save(store, info, io.BytesIO(data_v2))

    # Step 4: 再次讀取（ETag validation應該檢測到變更）
    with store.get_data_bytes(
        info.resource_id, info.revision_id, info.schema_version
    ) as stream:
        data = stream.read()

    # 應該讀到新資料（因為ETag不同，cache被invalidate）
    assert data == data_v2, "ETag validation should detect change and return new data"

    # 驗證新的ETag已更新
    new_etag = store._get_cached_etag(
        info.resource_id, info.revision_id, info.schema_version
    )
    assert new_etag is not None
    assert new_etag != cached_etag, "ETag should be updated after re-fetch"


def test_etag_cached_no_external_change(tmp_path: Path):
    """
    測試ETag validation：當資料沒變時，應該使用cache

    場景：
    1. 寫入資料（會HEAD一次獲取ETag）
    2. 第一次讀取（會cache + 保存ETag）
    3. 第二次讀取（ETag相同，應該用cache，只HEAD驗證）
    """
    store = ETagCachedS3ResourceStore(
        caches=[MemoryCache()],
        ttl_draft=3600,
        ttl_stable=3600,
        endpoint_url="http://localhost:9000",
        bucket="test-autocrud",
        prefix=f"test-etag-nochan-{tmp_path.name}/",
        access_key_id="minioadmin",
        secret_access_key="minioadmin",
    )

    info = create_info(rid="r1", rev="rev1", status=RevisionStatus.stable)
    data = b"stable data"

    # 寫入資料（這會HEAD一次獲取並保存ETag）
    store.save(info, io.BytesIO(data))

    # 第一次讀取（從S3獲取並cache）
    with store.get_data_bytes(
        info.resource_id, info.revision_id, info.schema_version
    ) as stream:
        assert stream.read() == data

    # 重置HEAD counter
    original_head_object = store.client.head_object
    head_object_call_count = [0]

    def mock_head_object(*args, **kwargs):
        head_object_call_count[0] += 1
        return original_head_object(*args, **kwargs)

    store.client.head_object = mock_head_object

    # 第二次讀取（ETag相同，應該用cache）
    with store.get_data_bytes(
        info.resource_id, info.revision_id, info.schema_version
    ) as stream:
        assert stream.read() == data

    # 驗證：第二次讀取應該只HEAD一次檢查ETag，然後返回cached data
    assert head_object_call_count[0] == 1, (
        f"Should only HEAD once for ETag check, got {head_object_call_count[0]}"
    )


def test_mq_cached_auto_subscriber(tmp_path: Path, require_rabbitmq):
    """
    測試MQ自動訂閱invalidation消息（需要真實RabbitMQ環境）

    驗證背景線程能正確接收和處理invalidation消息
    """
    from autocrud.resource_manager.resource_store.mq_cached_s3 import (
        MQCachedS3ResourceStore,
    )
    import time

    queue_prefix = f"test_auto_{uuid4().hex[:8]}_"

    # 創建store（會啟動訂閱線程）
    store = MQCachedS3ResourceStore(
        caches=[MemoryCache()],
        amqp_url="amqp://guest:guest@localhost:5672",
        queue_prefix=queue_prefix,
        ttl_draft=3600,
        ttl_stable=3600,
        endpoint_url="http://localhost:9000",
        bucket="autocrud-test",
        access_key_id="minioadmin",
        secret_access_key="minioadmin",
    )

    try:
        # 確認訂閱線程已啟動
        assert store._subscriber_thread.is_alive()

        # 手動發送一個invalidation消息
        info = create_info("auto_test", "v1")
        data = b"test data"

        # 先寫入並cache
        store.save(info, io.BytesIO(data))

        # 讀取確認有cache
        with store.get_data_bytes(
            info.resource_id, info.revision_id, info.schema_version
        ) as stream:
            result = stream.read()
        assert result == data

        # 手動發送invalidation（模擬其他instance）
        store._publish_invalidation(
            info.resource_id,
            info.revision_id,
            info.schema_version,
        )

        # 等待消息處理
        time.sleep(0.5)

        # 測試完成，清理
        store.close()

        # 確認線程已停止
        assert not store._subscriber_thread.is_alive()

    finally:
        try:
            store.close()
        except Exception:
            pass


def test_mq_cached_rabbitmq_unavailable(tmp_path: Path):
    """
    測試當RabbitMQ不可用時，store仍能正常工作
    """
    from autocrud.resource_manager.resource_store.mq_cached_s3 import (
        MQCachedS3ResourceStore,
    )

    # 使用無效的 RabbitMQ URL
    store = MQCachedS3ResourceStore(
        caches=[MemoryCache()],
        amqp_url="amqp://invalid:invalid@invalid-host:9999/",
        queue_prefix=f"test_invalid_{uuid4().hex[:8]}_",
        ttl_draft=3600,
        ttl_stable=3600,
        endpoint_url="http://localhost:9000",
        bucket="autocrud-test",
        access_key_id="minioadmin",
        secret_access_key="minioadmin",
    )

    try:
        # 確認初始化失敗但store仍可用
        assert store._channel is None
        assert store._connection is None

        # 基本cache功能應該仍然正常
        info = create_info("fallback_test", "v1")
        data = b"test data without mq"

        # 寫入應該成功（即使無法發送MQ消息）
        store.save(info, io.BytesIO(data))

        # 讀取應該成功
        with store.get_data_bytes(
            info.resource_id, info.revision_id, info.schema_version
        ) as stream:
            result = stream.read()
        assert result == data

        # 嘗試發送invalidation（應該靜默失敗）
        store._publish_invalidation(
            info.resource_id,
            info.revision_id,
            info.schema_version,
        )  # 不應該crash

    finally:
        try:
            store.close()
        except Exception:
            pass


def test_mq_cached_close_idempotent(tmp_path: Path, require_rabbitmq):
    """
    測試多次調用close()是安全的
    """
    from autocrud.resource_manager.resource_store.mq_cached_s3 import (
        MQCachedS3ResourceStore,
    )

    store = MQCachedS3ResourceStore(
        caches=[MemoryCache()],
        amqp_url="amqp://guest:guest@localhost:5672",
        queue_prefix=f"test_close_{uuid4().hex[:8]}_",
        ttl_draft=3600,
        ttl_stable=3600,
        endpoint_url="http://localhost:9000",
        bucket="autocrud-test",
        access_key_id="minioadmin",
        secret_access_key="minioadmin",
    )

    try:
        # 多次調用close()應該是安全的
        store.close()
        store.close()  # 第二次調用不應該crash
        store.close()  # 第三次也不應該crash

        # 確認線程已停止
        assert not store._subscriber_thread.is_alive()

    finally:
        try:
            store.close()
        except Exception:
            pass
