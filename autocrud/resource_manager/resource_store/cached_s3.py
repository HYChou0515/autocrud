from collections.abc import Generator
from contextlib import contextmanager
from typing import IO
import io

from autocrud.resource_manager.resource_store.s3 import S3ResourceStore
from autocrud.resource_manager.resource_store.cache import ICache
from autocrud.types import RevisionInfo, RevisionStatus


class CachedS3ResourceStore(S3ResourceStore):
    def __init__(
        self,
        caches: list[ICache] | None = None,
        ttl_draft: int = 60,  # 1 minute for drafts
        ttl_stable: int = 3600,  # 1 hour for stable
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.caches = caches or []
        self.ttl_draft = ttl_draft
        self.ttl_stable = ttl_stable

    def _get_ttl(self, info: RevisionInfo) -> int | None:
        if info.status == RevisionStatus.draft:
            return self.ttl_draft
        elif info.status == RevisionStatus.stable:
            return self.ttl_stable
        return None

    def get_revision_info(
        self,
        resource_id: str,
        revision_id: str,
        schema_version: str | None,
    ) -> RevisionInfo:
        # Check caches
        for cache in self.caches:
            info = cache.get_revision_info(resource_id, revision_id, schema_version)
            if info:
                return info

        # Cache miss
        info = super().get_revision_info(resource_id, revision_id, schema_version)

        # Populate caches
        ttl = self._get_ttl(info)
        for cache in self.caches:
            cache.put_revision_info(info, ttl=ttl)

        return info

    @contextmanager
    def get_data_bytes(
        self,
        resource_id: str,
        revision_id: str,
        schema_version: str | None,
    ) -> Generator[IO[bytes], None, None]:
        # Check caches
        for cache in self.caches:
            stream = cache.get_data(resource_id, revision_id, schema_version)
            if stream:
                try:
                    yield stream
                finally:
                    stream.close()
                return

        # Cache miss
        # We need info to decide TTL, so fetch it first
        # Optimziation: S3ResourceStore's get_data_bytes fetches UID then data.
        # But we don't have revision info here (status specifically).
        # We might need to fetch info to decide TTL if we want exact TTL based on status.
        # However, fetching info is an extra call.
        # If we skip TTL based on status for data, we risk caching draft data too long.
        # Let's try to get info from cache or store.

        try:
            info = self.get_revision_info(resource_id, revision_id, schema_version)
            ttl = self._get_ttl(info)
        except Exception:
            # If we fail to get info, default to draft TTL (safety first)
            ttl = self.ttl_draft

        with super().get_data_bytes(resource_id, revision_id, schema_version) as stream:
            data = stream.read()

            # Populate caches
            for cache in self.caches:
                cache.put_data(resource_id, revision_id, schema_version, data, ttl=ttl)

            yield io.BytesIO(data)

    def save(self, info: RevisionInfo, data: IO[bytes]) -> None:
        # We need to read data to save to S3 AND cache.
        # But stream can be read only once.
        # So we read to memory first.
        content = data.read()

        # Save to S3 using BytesIO
        super().save(info, io.BytesIO(content))

        # Save to caches
        ttl = self._get_ttl(info)
        for cache in self.caches:
            # We invalidate (delete) old entry implicitly by overwriting.
            # But explicit invalidation might be cleaner if cache doesn't support overwrite well.
            # Here put is overwrite.
            cache.put_revision_info(info, ttl=ttl)
            cache.put_data(
                info.resource_id,
                info.revision_id,
                info.schema_version,
                content,
                ttl=ttl,
            )

    def invalidate(
        self, resource_id: str, revision_id: str, schema_version: str | None
    ) -> None:
        """Explicitly invalidate cache entries."""
        for cache in self.caches:
            cache.delete(resource_id, revision_id, schema_version)
