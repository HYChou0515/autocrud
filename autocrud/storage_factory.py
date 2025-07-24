"""Storage Factory - 為資源創建獨立的存儲後端"""

from typing import Type, Optional, Callable, Any, Dict
from .storage import Storage, MemoryStorage, DiskStorage


class StorageFactory:
    """存儲工廠類，用於為不同資源創建獨立的存儲後端"""

    def __init__(
        self,
        storage_type: Type[Storage] = MemoryStorage,
        storage_config: Optional[Dict[str, Any]] = None,
        custom_factory: Optional[Callable[[str], Storage]] = None,
    ):
        """
        初始化存儲工廠

        Args:
            storage_type: 默認的存儲類型
            storage_config: 存儲配置參數
            custom_factory: 自定義的存儲創建函數，接收 resource_name 參數
        """
        self.storage_type = storage_type
        self.storage_config = storage_config or {}
        self.custom_factory = custom_factory

    def create_storage(self, resource_name: str) -> Storage:
        """
        為指定資源創建獨立的存儲後端

        Args:
            resource_name: 資源名稱

        Returns:
            新創建的存儲實例
        """
        if self.custom_factory:
            return self.custom_factory(resource_name)

        # 使用默認的存儲類型創建實例
        if self.storage_type == DiskStorage:
            # 為 DiskStorage 創建基於資源名稱的目錄路徑
            config = self.storage_config.copy()
            if "base_dir" not in config:
                config["base_dir"] = f"data/{resource_name}"
            return self.storage_type(**config)
        else:
            # 為其他存儲類型使用配置
            return self.storage_type(**self.storage_config)


class DefaultStorageFactory:
    """默認存儲工廠的便利類"""

    @staticmethod
    def memory() -> StorageFactory:
        """創建內存存儲工廠"""
        return StorageFactory(storage_type=MemoryStorage)

    @staticmethod
    def disk(base_dir: str = "data") -> StorageFactory:
        """
        創建磁盤存儲工廠

        Args:
            base_dir: 數據文件的基礎目錄

        Returns:
            配置好的磁盤存儲工廠
        """

        def disk_factory(resource_name: str) -> DiskStorage:
            import os

            resource_dir = os.path.join(base_dir, resource_name)
            return DiskStorage(base_dir=resource_dir)

        return StorageFactory(custom_factory=disk_factory)

    @staticmethod
    def custom(factory_func: Callable[[str], Storage]) -> StorageFactory:
        """
        創建自定義存儲工廠

        Args:
            factory_func: 自定義的存儲創建函數

        Returns:
            配置好的自定義存儲工廠
        """
        return StorageFactory(custom_factory=factory_func)
