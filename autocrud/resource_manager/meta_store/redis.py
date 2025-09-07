from collections.abc import Generator, Iterable
from contextlib import contextmanager

import redis
from msgspec import UNSET

from autocrud.resource_manager.basic import (
    Encoding,
    IFastMetaStore,
    MsgspecSerializer,
    get_sort_fn,
    is_match_query,
)
from autocrud.types import ResourceMeta, ResourceMetaSearchQuery


class RedisMetaStore(IFastMetaStore):
    def __init__(
        self,
        redis_url: str,
        encoding: Encoding = Encoding.json,
        prefix: str = "",
    ):
        self._serializer = MsgspecSerializer(
            encoding=encoding,
            resource_type=ResourceMeta,
        )
        self._redis = redis.Redis.from_url(redis_url)
        self._key_prefix = f"{prefix}resource_meta:"

    def _get_key(self, pk: str) -> str:
        return f"{self._key_prefix}{pk}"

    def __getitem__(self, pk: str) -> ResourceMeta:
        key = self._get_key(pk)
        data = self._redis.get(key)
        if data is None:
            raise KeyError(pk)
        return self._serializer.decode(data)

    def __setitem__(self, pk: str, meta: ResourceMeta) -> None:
        key = self._get_key(pk)
        data = self._serializer.encode(meta)
        self._redis.set(key, data)

    def __delitem__(self, pk: str) -> None:
        key = self._get_key(pk)
        result = self._redis.delete(key)
        if result == 0:
            raise KeyError(pk)

    def __iter__(self) -> Generator[str]:
        pattern = f"{self._key_prefix}*"
        for key in self._redis.scan_iter(match=pattern):
            key_str = key.decode("utf-8") if isinstance(key, bytes) else key
            yield key_str[len(self._key_prefix) :]

    def __len__(self) -> int:
        pattern = f"{self._key_prefix}*"
        return len(list(self._redis.scan_iter(match=pattern)))

    @contextmanager
    def get_then_delete(self) -> Generator[Iterable[ResourceMeta]]:
        """获取所有元数据然后删除，用于快速存储的批量同步"""
        metas = []
        pattern = f"{self._key_prefix}*"

        # 收集所有数据
        for key in self._redis.scan_iter(match=pattern):
            data = self._redis.get(key)
            if data:
                meta = self._serializer.decode(data)
                metas.append(meta)

        try:
            yield metas
            # 如果成功，清空所有数据
            if metas:
                keys = list(self._redis.scan_iter(match=pattern))
                if keys:
                    self._redis.delete(*keys)
        except Exception:
            # 如果出现异常，不删除数据
            raise

    def iter_search(self, query: ResourceMetaSearchQuery) -> Generator[ResourceMeta]:
        results: list[ResourceMeta] = []
        pattern = f"{self._key_prefix}*"
        for key in self._redis.scan_iter(match=pattern):
            data = self._redis.get(key)
            if data:
                meta = self._serializer.decode(data)
                if is_match_query(meta, query):
                    results.append(meta)
        results.sort(key=get_sort_fn([] if query.sorts is UNSET else query.sorts))
        yield from results[query.offset : query.offset + query.limit]
