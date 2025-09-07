import threading
from collections.abc import Generator

from autocrud.resource_manager.basic import (
    IFastMetaStore,
    IMetaStore,
    ISlowMetaStore,
)
from autocrud.types import ResourceMeta, ResourceMetaSearchQuery


class FastSlowMetaStore(IMetaStore):
    def __init__(
        self,
        fast_store: IFastMetaStore,
        slow_store: ISlowMetaStore,
        sync_interval: int = 1,
    ):
        self._fast_store = fast_store
        self._slow_store = slow_store
        self._sync_interval = sync_interval
        self._sync_thread = None
        self._stop_sync = threading.Event()

        # 启动后台同步线程
        self._start_background_sync()

    def _start_background_sync(self):
        """启动后台同步线程"""
        if self._sync_thread is None or not self._sync_thread.is_alive():
            self._stop_sync.clear()
            self._sync_thread = threading.Thread(
                target=self._background_sync_worker,
                daemon=True,
            )
            self._sync_thread.start()

    def _background_sync_worker(self):
        """后台同步工作线程"""
        while not self._stop_sync.wait(self._sync_interval):
            try:
                self._sync_fast_to_slow()
            except Exception as e:
                # 记录错误但不中断线程
                print(f"Background sync error: {e}")

    def _sync_fast_to_slow(self):
        """从快速存储同步到慢速存储"""
        with self._fast_store.get_then_delete() as metas:
            if not metas:
                return
            self._slow_store.save_many(metas)

    def force_sync(self):
        """手动触发同步，主要用于测试"""
        self._sync_fast_to_slow()

    def __getitem__(self, pk: str) -> ResourceMeta:
        # 先檢查 Fast 存儲
        try:
            return self._fast_store[pk]
        except KeyError:
            # 如果 Fast 存儲 中沒有，從慢速存儲查詢
            return self._slow_store[pk]

    def __setitem__(self, pk: str, meta: ResourceMeta) -> None:
        # 只寫入 Fast 存儲
        self._fast_store[pk] = meta

    def __delitem__(self, pk: str) -> None:
        # 先尝试从 Fast 存储删除
        try:
            del self._fast_store[pk]
        except KeyError:
            # 如果 Fast 存儲 中沒有，從慢速存儲刪除
            del self._slow_store[pk]

    def __iter__(self) -> Generator[str]:
        # 不再主动同步，依赖后台同步线程
        # 直接从 slow 存储获取迭代器
        yield from self._slow_store

    def __len__(self) -> int:
        # 不再主动同步，依赖后台同步线程
        # 直接从 slow 存储获取长度
        return len(self._slow_store)

    def iter_search(self, query: ResourceMetaSearchQuery) -> Generator[ResourceMeta]:
        self._sync_fast_to_slow()
        return self._slow_store.iter_search(query)
