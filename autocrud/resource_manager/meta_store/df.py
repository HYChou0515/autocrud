import sys
from collections.abc import Generator

from msgspec import UNSET

from autocrud.types import ResourceMeta, ResourceMetaSearchQuery

try:
    import pandas as pd
except ImportError:
    print("Pandas is required to use DFMemoryMetaStore", file=sys.stderr)
    raise

from autocrud.resource_manager.basic import (
    Encoding,
    ISlowMetaStore,
    MsgspecSerializer,
    get_sort_fn,
)


class DFMemoryMetaStore(ISlowMetaStore):
    def __init__(self, encoding: Encoding = Encoding.json):
        self._serializer = MsgspecSerializer(
            encoding=encoding,
            resource_type=ResourceMeta,
        )
        self._store: dict[str, bytes] = {}
        self._df = pd.DataFrame(
            columns=[
                "created_time",
                "updated_time",
                "created_by",
                "updated_by",
                "is_deleted",
            ],
            index=pd.Index([], dtype="object", name="resource_id"),
        )
        self._updated: set[str] = set()

    def __getitem__(self, pk: str) -> ResourceMeta:
        return self._serializer.decode(self._store[pk])

    def _update_df(self) -> None:
        if not self._updated:
            return
        values = []
        for pk in self._updated:
            b = self._serializer.decode(self._store[pk])
            values.append(
                {
                    "resource_id": b.resource_id,
                    "created_time": b.created_time,
                    "updated_time": b.updated_time,
                    "created_by": b.created_by,
                    "updated_by": b.updated_by,
                    "is_deleted": b.is_deleted,
                },
            )
        udf = pd.DataFrame(values).set_index("resource_id")
        news = udf.index.difference(self._df.index)
        old = udf.index.intersection(self._df.index)
        if not news.empty:
            self._df = pd.concat([self._df, udf.loc[news]], axis=0)
        if not old.empty:
            self._df.loc[old] = udf.loc[old]
        self._updated.clear()

    def __setitem__(self, pk: str, b: ResourceMeta) -> None:
        # 更新序列化存儲
        self._store[pk] = self._serializer.encode(b)
        self._updated.add(pk)

        if len(self._updated) >= 8192:
            self._update_df()

    def __delitem__(self, pk: str) -> None:
        self._df.drop(index=pk, errors="ignore", inplace=True)
        del self._store[pk]

    def __iter__(self) -> Generator[str]:
        yield from self._store.keys()

    def __len__(self) -> int:
        return len(self._store)

    def iter_search(self, query: ResourceMetaSearchQuery) -> Generator[ResourceMeta]:
        self._update_df()
        exps: list[str] = []
        if query.is_deleted is not UNSET:
            exps.append("is_deleted == @query.is_deleted")
        if query.created_time_start is not UNSET:
            exps.append("created_time >= @query.created_time_start")
        if query.created_time_end is not UNSET:
            exps.append("created_time <= @query.created_time_end")
        if query.updated_time_start is not UNSET:
            exps.append("updated_time >= @query.updated_time_start")
        if query.updated_time_end is not UNSET:
            exps.append("updated_time <= @query.updated_time_end")
        if query.created_bys is not UNSET:
            exps.append("created_by.isin(@query.created_bys)")
        if query.updated_bys is not UNSET:
            exps.append("updated_by.isin(@query.updated_bys)")
        query_str = " and ".join(exps) if exps else "True"
        results: list[ResourceMeta] = []
        for pk in self._df.query(query_str).index:
            meta_b = self._store[pk]
            meta = self._serializer.decode(meta_b)
            results.append(meta)
        results.sort(key=get_sort_fn([] if query.sorts is UNSET else query.sorts))
        yield from results[query.offset : query.offset + query.limit]
