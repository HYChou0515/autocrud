"""
ETag-based CachedS3ResourceStore

使用S3的ETag機制進行cache validation
"""

import io
from collections.abc import Generator
from contextlib import contextmanager
from typing import IO

from autocrud.resource_manager.resource_store.cache import ICache
from autocrud.resource_manager.resource_store.cached_s3 import CachedS3ResourceStore
from autocrud.types import RevisionInfo


class ETagCachedS3ResourceStore(CachedS3ResourceStore):
    """
    使用ETag進行cache validation的CachedS3ResourceStore

    特點：
    - 讀取時先用HEAD請求檢查S3的ETag
    - 如果ETag與cache中的相同，直接返回cached data
    - 如果ETag不同，invalidate cache並重新獲取
    - 比每次都GET完整資料更有效率

    工作原理：
    1. Cache中保存data + ETag
    2. 讀取時先HEAD檢查ETag（便宜的操作）
    3. ETag相同 → 返回cached data（節省傳輸）
    4. ETag不同 → invalidate + 重新GET（保證正確性）

    Example:
        store = ETagCachedS3ResourceStore(
            caches=[MemoryCache()],
            access_key_id="...",
            secret_access_key="...",
        )
    """

    def __init__(
        self,
        caches: list[ICache],
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
        初始化ETag-based Cached S3 Resource Store

        Args:
            caches: Cache層列表（如MemoryCache, DiskCache）
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

        # ETag會使用cache的put_data接口存儲
        # 不假設cache的具體實現

    def _get_etag_key(
        self, resource_id: str, revision_id: str, schema_version: str | None
    ) -> str:
        """構建ETag cache key"""
        sv = schema_version or "no_ver"
        return f"etag:{resource_id}/{revision_id}/{sv}"

    def _get_cached_etag(
        self, resource_id: str, revision_id: str, schema_version: str | None
    ) -> str | None:
        """從cache中獲取保存的ETag"""
        # 使用特殊的resource_id格式來存儲ETag
        etag_resource_id = self._get_etag_key(resource_id, revision_id, schema_version)

        # 嘗試從所有cache層讀取ETag
        for cache in self.caches:
            stream = cache.get_data(etag_resource_id, "etag", None)
            if stream:
                try:
                    etag = stream.read().decode("utf-8")
                    return etag
                finally:
                    stream.close()
        return None

    def _save_etag(
        self,
        resource_id: str,
        revision_id: str,
        schema_version: str | None,
        etag: str,
        ttl: int | None = None,
    ):
        """保存ETag到cache"""
        # 使用特殊的resource_id格式來存儲ETag
        etag_resource_id = self._get_etag_key(resource_id, revision_id, schema_version)
        etag_bytes = etag.encode("utf-8")

        # 保存到所有cache層
        for cache in self.caches:
            cache.put_data(etag_resource_id, "etag", None, etag_bytes, ttl=ttl)

    def _check_etag_validity(
        self,
        resource_id: str,
        revision_id: str,
        schema_version: str | None,
    ) -> bool:
        """
        檢查cache中的ETag是否仍然有效

        Returns:
            True: cache有效，可以使用
            False: cache無效，需要重新獲取
        """
        # 獲取cached ETag
        cached_etag = self._get_cached_etag(resource_id, revision_id, schema_version)
        if not cached_etag:
            # 沒有cached ETag，無法驗證
            return False

        try:
            # 嘗試從revision info cache獲取UID（避免額外S3調用）
            info = None
            for cache in self.caches:
                info = cache.get_revision_info(resource_id, revision_id, schema_version)
                if info:
                    break

            if not info:
                # 沒有cached revision info，需要從S3獲取
                # 這會調用get_object，但總比每次都調用好
                resource_key = self._get_resource_key(
                    resource_id, revision_id, schema_version
                )
                try:
                    response = self.client.get_object(
                        Bucket=self.bucket, Key=resource_key
                    )
                    uid = response["Body"].read().decode("utf-8")
                except Exception:
                    # 如果獲取UID失敗，認為cache無效
                    return False
            else:
                uid = str(info.uid)

            # 用HEAD請求檢查data的ETag（只是metadata查詢，不下載資料）
            data_key = self._get_raw_data_key(uid)
            head_response = self.client.head_object(Bucket=self.bucket, Key=data_key)
            s3_etag = head_response.get("ETag", "").strip('"')

            # 比較ETag
            return cached_etag == s3_etag

        except Exception:
            # 如果檢查失敗（如網絡錯誤），保守起見認為cache有效
            # 這樣至少可以在S3不可用時還能用cache
            return True

    @contextmanager
    def get_data_bytes(
        self,
        resource_id: str,
        revision_id: str,
        schema_version: str | None,
    ) -> Generator[IO[bytes], None, None]:
        """
        獲取資源資料，使用ETag進行cache validation

        流程：
        1. 嘗試從cache讀取
        2. 如果cache hit，用HEAD檢查ETag是否有效
        3. ETag有效 → 返回cached data
        4. ETag無效 → invalidate cache並從S3重新讀取
        """
        # 先嘗試從cache讀取
        for cache in self.caches:
            stream = cache.get_data(resource_id, revision_id, schema_version)
            if stream is not None:
                # Cache hit！檢查ETag是否有效
                if self._check_etag_validity(resource_id, revision_id, schema_version):
                    # ETag有效，返回cached data
                    try:
                        yield stream
                    finally:
                        stream.close()
                    return
                else:
                    # ETag無效，清除cache並繼續從S3讀取
                    stream.close()
                    self.invalidate(resource_id, revision_id, schema_version)
                    break

        # Cache miss或ETag無效，從S3讀取
        # 獲取TTL
        try:
            info = self.get_revision_info(resource_id, revision_id, schema_version)
            ttl = self._get_ttl(info)
        except Exception:
            # If we fail to get info, default to draft TTL (safety first)
            ttl = self.ttl_draft

        with super().get_data_bytes(resource_id, revision_id, schema_version) as stream:
            # 讀取資料
            data = stream.read()

            # 獲取並保存ETag
            try:
                resource_key = self._get_resource_key(
                    resource_id, revision_id, schema_version
                )
                response = self.client.get_object(Bucket=self.bucket, Key=resource_key)
                uid = response["Body"].read().decode("utf-8")
                data_key = self._get_raw_data_key(uid)

                # 獲取ETag
                head_response = self.client.head_object(
                    Bucket=self.bucket, Key=data_key
                )
                etag = head_response.get("ETag", "").strip('"')

                # 保存ETag到cache
                self._save_etag(resource_id, revision_id, schema_version, etag, ttl)
            except Exception:
                # 保存ETag失敗不影響主流程
                pass

            # Populate data cache
            for cache in self.caches:
                cache.put_data(resource_id, revision_id, schema_version, data, ttl=ttl)

            # 返回data stream
            yield io.BytesIO(data)

    def save(self, info: RevisionInfo, data: IO[bytes]) -> None:
        """保存資源並記錄ETag"""
        # 先保存到S3
        super().save(info, data)

        # 獲取並保存ETag
        try:
            uid = str(info.uid)
            data_key = self._get_raw_data_key(uid)

            # 獲取剛寫入的object的ETag
            head_response = self.client.head_object(Bucket=self.bucket, Key=data_key)
            etag = head_response.get("ETag", "").strip('"')

            # 保存ETag
            ttl = self._get_ttl(info)
            self._save_etag(
                info.resource_id,
                info.revision_id,
                info.schema_version,
                etag,
                ttl,
            )
        except Exception:
            # 保存ETag失敗不影響主流程
            pass
