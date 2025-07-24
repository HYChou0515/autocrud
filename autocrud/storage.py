"""存儲抽象層"""

import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from .serializer import Serializer, SerializerFactory


class Storage(ABC):
    """存儲抽象基類"""

    def __init__(self, serializer: Optional[Serializer] = None):
        if serializer is None:
            serializer = SerializerFactory.create("json")
        self.serializer = serializer

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """獲取數據"""
        pass

    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        """存儲數據"""
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """刪除數據"""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """檢查鍵是否存在"""
        pass

    @abstractmethod
    def list_keys(self) -> List[str]:
        """列出所有鍵"""
        pass


class MemoryStorage(Storage):
    """純內存存儲實現（重啟後數據消失，適合測試和演示）"""

    def __init__(self, serializer: Optional[Serializer] = None):
        super().__init__(serializer)
        self._data: Dict[str, bytes] = {}

    def get(self, key: str) -> Optional[Any]:
        if key not in self._data:
            return None

        serialized_data = self._data[key]
        return self.serializer.deserialize(serialized_data)

    def set(self, key: str, value: Any) -> None:
        serialized_data = self.serializer.serialize(value)
        self._data[key] = serialized_data

    def delete(self, key: str) -> bool:
        if key in self._data:
            del self._data[key]
            return True
        return False

    def exists(self, key: str) -> bool:
        return key in self._data

    def list_keys(self) -> List[str]:
        return list(self._data.keys())

    def clear(self) -> None:
        """清空所有數據"""
        self._data.clear()

    def size(self) -> int:
        """獲取存儲的條目數量"""
        return len(self._data)


class DiskStorage(Storage):
    """硬碟檔案儲存實作（真正的持久化儲存）"""

    def __init__(self, base_dir: str, serializer: Optional[Serializer] = None):
        super().__init__(serializer)
        self.base_dir = base_dir

        # 確保基礎目錄存在
        os.makedirs(self.base_dir, exist_ok=True)

    def _get_file_path(self, key: str) -> str:
        """獲取鍵對應的文件路徑"""
        # 將鍵轉換為安全的文件名
        safe_key = key.replace(":", "_").replace("/", "_")
        return os.path.join(self.base_dir, f"{safe_key}.data")

    def get(self, key: str) -> Optional[Any]:
        file_path = self._get_file_path(key)
        if not os.path.exists(file_path):
            return None

        try:
            with open(file_path, "rb") as f:
                serialized_data = f.read()
            return self.serializer.deserialize(serialized_data)
        except Exception as e:
            print(f"讀取文件失敗 {file_path}: {e}")
            return None

    def set(self, key: str, value: Any) -> None:
        file_path = self._get_file_path(key)

        try:
            serialized_data = self.serializer.serialize(value)
            with open(file_path, "wb") as f:
                f.write(serialized_data)
        except Exception as e:
            print(f"寫入文件失敗 {file_path}: {e}")
            raise

    def delete(self, key: str) -> bool:
        file_path = self._get_file_path(key)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                return True
            except Exception as e:
                print(f"刪除文件失敗 {file_path}: {e}")
                return False
        return False

    def exists(self, key: str) -> bool:
        file_path = self._get_file_path(key)
        return os.path.exists(file_path)

    def list_keys(self) -> List[str]:
        """列出所有鍵"""
        keys = []
        try:
            for filename in os.listdir(self.base_dir):
                if filename.endswith(".data"):
                    # 將文件名轉換回鍵名
                    key = filename[:-5].replace("_", ":")  # 移除 .data 後綴
                    keys.append(key)
        except Exception as e:
            print(f"列出文件失敗: {e}")

        return keys

    def clear(self) -> None:
        """清空所有數據"""
        try:
            for filename in os.listdir(self.base_dir):
                if filename.endswith(".data"):
                    file_path = os.path.join(self.base_dir, filename)
                    os.remove(file_path)
        except Exception as e:
            print(f"清空目錄失敗: {e}")

    def size(self) -> int:
        """獲取存儲的條目數量"""
        return len(self.list_keys())


# 使用範例
if __name__ == "__main__":
    # 測試純內存存儲
    print("=== 測試純內存存儲 ===")
    memory_storage = MemoryStorage()

    # 測試數據
    test_data = {"name": "Alice", "age": 30}

    # 存儲數據
    memory_storage.set("user:1", test_data)
    print(f"內存存儲成功: {memory_storage.exists('user:1')}")

    # 獲取數據
    retrieved_data = memory_storage.get("user:1")
    print(f"內存獲取數據: {retrieved_data}")

    print(f"內存存儲大小: {memory_storage.size()}")

    # 測試硬碟儲存
    print("\n=== 測試硬碟儲存 ===")
    import tempfile

    temp_dir = tempfile.mkdtemp()
    disk_storage = DiskStorage(temp_dir)

    # 儲存資料
    disk_storage.set("user:1", test_data)
    print(f"硬碟儲存成功: {disk_storage.exists('user:1')}")

    # 取得資料
    retrieved_data = disk_storage.get("user:1")
    print(f"硬碟取得資料: {retrieved_data}")

    print(f"硬碟儲存大小: {disk_storage.size()}")
    print(f"硬碟所有鍵: {disk_storage.list_keys()}")

    # 清理
    disk_storage.clear()
    os.rmdir(temp_dir)
