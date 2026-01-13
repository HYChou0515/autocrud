"""
Message Queue based CachedS3ResourceStore

使用RabbitMQ進行跨instance的cache invalidation
"""

import json
import threading
from typing import IO

from autocrud.resource_manager.resource_store.cache import ICache
from autocrud.resource_manager.resource_store.cached_s3 import CachedS3ResourceStore
from autocrud.types import RevisionInfo


class MQCachedS3ResourceStore(CachedS3ResourceStore):
    """
    使用RabbitMQ進行cache invalidation的CachedS3ResourceStore

    特點：
    - 寫入時發送invalidation message到RabbitMQ
    - 訂閱RabbitMQ接收其他instance的invalidation message
    - 收到message後自動清除本地cache
    - 無需每次讀取時check S3，效率最高

    Example:
        store = MQCachedS3ResourceStore(
            caches=[MemoryCache()],
            amqp_url="amqp://guest:guest@localhost:5672/",
            queue_prefix="autocrud:",
            access_key_id="...",
            secret_access_key="...",
        )
    """

    def __init__(
        self,
        caches: list[ICache],
        amqp_url: str = "amqp://guest:guest@localhost:5672/",
        queue_prefix: str = "autocrud:",
        *,
        ttl_draft: int = 60,
        ttl_stable: int = 3600,
        endpoint_url: str | None = None,
        bucket: str = "autocrud",
        prefix: str = "",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        region_name: str | None = None,
    ):
        """
        初始化MQ-based Cached S3 Resource Store

        Args:
            caches: Cache層列表（如MemoryCache, DiskCache）
            amqp_url: RabbitMQ連接URL
            queue_prefix: Queue名稱前綴
            ttl_draft: Draft狀態資源的cache TTL（秒）
            ttl_stable: Stable狀態資源的cache TTL（秒）
            endpoint_url: S3 endpoint URL（用於MinIO等S3兼容服務）
            bucket: S3 bucket名稱
            prefix: S3 key prefix
            access_key_id: AWS access key ID
            secret_access_key: AWS secret access key
            region_name: AWS region name
        """
        super().__init__(
            caches=caches,
            ttl_draft=ttl_draft,
            ttl_stable=ttl_stable,
            endpoint_url=endpoint_url,
            bucket=bucket,
            prefix=prefix,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            region_name=region_name,
        )

        self.amqp_url = amqp_url
        self.queue_name = f"{queue_prefix}cache_invalidation"
        self._stop_subscriber = threading.Event()
        self._connection = None
        self._channel = None
        self._subscriber_connection = None
        self._subscriber_channel = None

        # 初始化RabbitMQ連接（用於publish）
        self._init_rabbitmq()

        # 啟動訂閱線程，接收其他instance的invalidation消息
        self._subscriber_thread = threading.Thread(
            target=self._subscribe_invalidation,
            daemon=True,
            name="MQCacheInvalidation",
        )
        self._subscriber_thread.start()

    def _init_rabbitmq(self):
        """初始化RabbitMQ連接"""
        try:
            import pika

            self._connection = pika.BlockingConnection(
                pika.URLParameters(self.amqp_url)
            )
            self._channel = self._connection.channel()
            self._channel.queue_declare(queue=self.queue_name, durable=True)
        except Exception:
            # 如果RabbitMQ不可用，靜默失敗
            # Cache仍然可以工作，只是沒有跨instance invalidation
            pass

    def _subscribe_invalidation(self):
        """訂閱invalidation消息，收到後清除本地cache"""
        try:
            import pika
        except ImportError:
            # pika未安裝，無法使用MQ功能
            return

        def on_message(ch, method, properties, body):
            try:
                message = json.loads(body.decode("utf-8"))
                resource_id = message.get("resource_id")
                revision_id = message.get("revision_id")
                schema_version = message.get("schema_version")

                if resource_id and revision_id:
                    # 清除本地cache
                    self.invalidate(resource_id, revision_id, schema_version)

                # 確認消息處理完成
                ch.basic_ack(delivery_tag=method.delivery_tag)
            except Exception:
                # 靜默處理錯誤，避免影響訂閱線程
                # 拒絕消息但不重新入隊
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        # 持續訂閱直到stop signal
        while not self._stop_subscriber.is_set():
            try:
                # 創建新的連接用於訂閱
                self._subscriber_connection = pika.BlockingConnection(
                    pika.URLParameters(self.amqp_url)
                )
                self._subscriber_channel = self._subscriber_connection.channel()
                self._subscriber_channel.queue_declare(
                    queue=self.queue_name, durable=True
                )

                # 設置QoS，一次只處理一條消息
                self._subscriber_channel.basic_qos(prefetch_count=1)

                # 開始消費
                self._subscriber_channel.basic_consume(
                    queue=self.queue_name, on_message_callback=on_message
                )

                # 開始blocking消費（會在stop時被中斷）
                self._subscriber_channel.start_consuming()

            except Exception:
                # 如果訂閱失敗，清理連接並短暫等待後重試
                try:
                    if self._subscriber_channel:
                        self._subscriber_channel.close()
                    if self._subscriber_connection:
                        self._subscriber_connection.close()
                except Exception:
                    pass

                self._stop_subscriber.wait(1.0)

    def _publish_invalidation(
        self, resource_id: str, revision_id: str, schema_version: str | None
    ):
        """發送invalidation消息到RabbitMQ，通知其他instance清除cache"""
        if not self._channel:
            return

        try:
            import pika

            message = {
                "resource_id": resource_id,
                "revision_id": revision_id,
                "schema_version": schema_version,
            }

            self._channel.basic_publish(
                exchange="",
                routing_key=self.queue_name,
                body=json.dumps(message).encode("utf-8"),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # 持久化消息
                ),
            )
        except Exception:
            # 發送失敗不應該影響主邏輯
            # 最壞情況下其他instance的cache會在TTL後過期
            # 嘗試重新初始化連接
            try:
                self._init_rabbitmq()
            except Exception:
                pass

    def save(self, info: RevisionInfo, data: IO[bytes]) -> None:
        """保存資源，並發送invalidation消息到RabbitMQ"""
        # 調用父類的save（會寫入S3和更新本地cache）
        super().save(info, data)

        # 發送invalidation消息，通知其他instance
        self._publish_invalidation(
            info.resource_id,
            info.revision_id,
            info.schema_version,
        )

    def close(self):
        """關閉訂閱線程和清理資源"""
        self._stop_subscriber.set()

        # 停止訂閱者的消費
        try:
            if self._subscriber_channel:
                self._subscriber_channel.stop_consuming()
        except Exception:
            pass

        # 等待訂閱線程結束
        if self._subscriber_thread.is_alive():
            self._subscriber_thread.join(timeout=2.0)

        # 關閉連接
        try:
            if self._subscriber_channel:
                self._subscriber_channel.close()
            if self._subscriber_connection:
                self._subscriber_connection.close()
            if self._channel:
                self._channel.close()
            if self._connection:
                self._connection.close()
        except Exception:
            pass

    def __del__(self):
        """析構時確保資源清理"""
        try:
            self.close()
        except Exception:
            pass
