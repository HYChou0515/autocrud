from abc import ABC, abstractmethod
from typing import IO
import io
import shutil
import time
import os
from pathlib import Path
from dataclasses import dataclass
from autocrud.types import RevisionInfo


class ICache(ABC):
    @abstractmethod
    def get_revision_info(
        self, resource_id: str, revision_id: str, schema_version: str | None
    ) -> RevisionInfo | None:
        """Retrieve revision metadata from cache."""

    @abstractmethod
    def put_revision_info(self, info: RevisionInfo, ttl: int | None = None) -> None:
        """Store revision metadata in cache.

        Args:
            info: The revision info to store.
            ttl: Time to live in seconds. None means no expiration.
        """

    @abstractmethod
    def get_data(
        self, resource_id: str, revision_id: str, schema_version: str | None
    ) -> IO[bytes] | None:
        """Retrieve resource data from cache as a binary stream.

        Returns None if the data is not in the cache or expired.
        The caller is responsible for closing the returned stream.
        """

    @abstractmethod
    def put_data(
        self,
        resource_id: str,
        revision_id: str,
        schema_version: str | None,
        data: bytes,
        ttl: int | None = None,
    ) -> None:
        """Store resource data in cache.

        Args:
            ttl: Time to live in seconds. None means no expiration.
        """

    @abstractmethod
    def delete(
        self, resource_id: str, revision_id: str, schema_version: str | None
    ) -> None:
        """Remove revision info and data from cache."""


@dataclass
class CacheEntry:
    data: bytes | RevisionInfo
    expires_at: float | None


class MemoryCache(ICache):
    def __init__(self):
        self._info_store: dict[str, CacheEntry] = {}
        self._data_store: dict[str, CacheEntry] = {}

    def _get_key(
        self, resource_id: str, revision_id: str, schema_version: str | None
    ) -> str:
        sv = schema_version if schema_version is not None else "None"
        return f"{resource_id}/{revision_id}/{sv}"

    def _is_expired(self, entry: CacheEntry) -> bool:
        if entry.expires_at is None:
            return False
        return time.time() > entry.expires_at

    def get_revision_info(
        self, resource_id: str, revision_id: str, schema_version: str | None
    ) -> RevisionInfo | None:
        key = self._get_key(resource_id, revision_id, schema_version)
        entry = self._info_store.get(key)
        if entry is None:
            return None
        if self._is_expired(entry):
            del self._info_store[key]
            return None
        return entry.data  # type: ignore

    def put_revision_info(self, info: RevisionInfo, ttl: int | None = None) -> None:
        key = self._get_key(info.resource_id, info.revision_id, info.schema_version)
        expires_at = time.time() + ttl if ttl is not None else None
        self._info_store[key] = CacheEntry(data=info, expires_at=expires_at)

    def get_data(
        self, resource_id: str, revision_id: str, schema_version: str | None
    ) -> IO[bytes] | None:
        key = self._get_key(resource_id, revision_id, schema_version)
        entry = self._data_store.get(key)
        if entry is None:
            return None
        if self._is_expired(entry):
            del self._data_store[key]
            return None
        return io.BytesIO(entry.data)  # type: ignore

    def put_data(
        self,
        resource_id: str,
        revision_id: str,
        schema_version: str | None,
        data: bytes,
        ttl: int | None = None,
    ) -> None:
        key = self._get_key(resource_id, revision_id, schema_version)
        expires_at = time.time() + ttl if ttl is not None else None
        self._data_store[key] = CacheEntry(data=data, expires_at=expires_at)

    def delete(
        self, resource_id: str, revision_id: str, schema_version: str | None
    ) -> None:
        key = self._get_key(resource_id, revision_id, schema_version)
        self._info_store.pop(key, None)
        self._data_store.pop(key, None)


class DiskCache(ICache):
    def __init__(self, cache_dir: str = "/tmp/autocrud_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # We need a serializer for RevisionInfo to store it on disk
        from autocrud.resource_manager.basic import MsgspecSerializer, Encoding

        self._info_serializer = MsgspecSerializer(
            encoding=Encoding.json,
            resource_type=RevisionInfo,
        )

    def _get_path(
        self, resource_id: str, revision_id: str, schema_version: str | None
    ) -> Path:
        sv = schema_version if schema_version is not None else "no_ver"
        # Avoid path traversal issues strictly speaking, but for now simplistic join
        return self.cache_dir / resource_id / revision_id / sv

    def _check_expiration(self, path: Path) -> bool:
        """Check if file is expired via .meta file or similar."""
        # Implementing expiration for disk cache
        expire_path = path.with_name(path.name + ".expire")
        if not expire_path.exists():
            return False  # No expiration

        try:
            with open(expire_path, "r") as f:
                expire_at = float(f.read().strip())
                if time.time() > expire_at:
                    try:
                        os.unlink(path)
                        os.unlink(expire_path)
                    except OSError:
                        pass
                    return True
        except (ValueError, OSError):
            return True  # Treat error as expired

        return False

    def _write_expiration(self, path: Path, ttl: int | None):
        expire_path = path.with_name(path.name + ".expire")
        if ttl is None:
            if expire_path.exists():
                expire_path.unlink(missing_ok=True)
        else:
            with open(expire_path, "w") as f:
                f.write(str(time.time() + ttl))

    def get_revision_info(
        self, resource_id: str, revision_id: str, schema_version: str | None
    ) -> RevisionInfo | None:
        path = self._get_path(resource_id, revision_id, schema_version) / "info"
        if not path.exists():
            return None

        if self._check_expiration(path):
            return None

        try:
            with open(path, "rb") as f:
                return self._info_serializer.decode(f.read())
        except Exception:
            # If read fails, treat as cache miss
            return None

    def put_revision_info(self, info: RevisionInfo, ttl: int | None = None) -> None:
        path = self._get_path(info.resource_id, info.revision_id, info.schema_version)
        path.mkdir(parents=True, exist_ok=True)
        file_path = path / "info"
        with open(file_path, "wb") as f:
            f.write(self._info_serializer.encode(info))
        self._write_expiration(file_path, ttl)

    def get_data(
        self, resource_id: str, revision_id: str, schema_version: str | None
    ) -> IO[bytes] | None:
        path = self._get_path(resource_id, revision_id, schema_version) / "data"
        if not path.exists():
            return None

        if self._check_expiration(path):
            return None

        try:
            return open(path, "rb")
        except Exception:
            return None

    def put_data(
        self,
        resource_id: str,
        revision_id: str,
        schema_version: str | None,
        data: bytes,
        ttl: int | None = None,
    ) -> None:
        path = self._get_path(resource_id, revision_id, schema_version)
        path.mkdir(parents=True, exist_ok=True)
        file_path = path / "data"
        with open(file_path, "wb") as f:
            f.write(data)
        self._write_expiration(file_path, ttl)

    def delete(
        self, resource_id: str, revision_id: str, schema_version: str | None
    ) -> None:
        path = self._get_path(resource_id, revision_id, schema_version)
        if path.exists():
            shutil.rmtree(path)

    def clear(self):
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
