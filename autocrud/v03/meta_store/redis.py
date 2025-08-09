from collections.abc import Generator
from msgspec import UNSET

from autocrud.v03.basic import (
    Encoding,
    IMetaStore,
    MsgspecSerializer,
    ResourceMeta,
    ResourceMetaSearchQuery,
    get_sort_fn,
    is_match_query,
)


import redis


class RedisMetaStore(IMetaStore):
    def __init__(self, client: redis.Redis, encoding: Encoding = Encoding.json):
        self._serializer = MsgspecSerializer(
            encoding=encoding, resource_type=ResourceMeta
        )
        self._client = client
        self._key_prefix = "resource_meta:"

    def _get_key(self, pk: str) -> str:
        return f"{self._key_prefix}{pk}"

    def __getitem__(self, pk: str) -> ResourceMeta:
        key = self._get_key(pk)
        data = self._client.get(key)
        if data is None:
            raise KeyError(pk)
        return self._serializer.decode(data)

    def __setitem__(self, pk: str, meta: ResourceMeta) -> None:
        key = self._get_key(pk)
        data = self._serializer.encode(meta)
        self._client.set(key, data)

    def __delitem__(self, pk: str) -> None:
        key = self._get_key(pk)
        result = self._client.delete(key)
        if result == 0:
            raise KeyError(pk)

    def __iter__(self) -> Generator[str]:
        pattern = f"{self._key_prefix}*"
        for key in self._client.scan_iter(match=pattern):
            key_str = key.decode("utf-8") if isinstance(key, bytes) else key
            yield key_str[len(self._key_prefix) :]

    def __len__(self) -> int:
        pattern = f"{self._key_prefix}*"
        return len(list(self._client.scan_iter(match=pattern)))

    def iter_search(self, query: ResourceMetaSearchQuery) -> Generator[ResourceMeta]:
        results: list[ResourceMeta] = []
        pattern = f"{self._key_prefix}*"
        for key in self._client.scan_iter(match=pattern):
            data = self._client.get(key)
            if data:
                meta = self._serializer.decode(data)
                if is_match_query(meta, query):
                    results.append(meta)
        results.sort(key=get_sort_fn([] if query.sorts is UNSET else query.sorts))
        yield from results[query.offset : query.offset + query.limit]
