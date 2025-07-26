"""提升 storage.py 覆蓋率的測試"""

import os
import tempfile
import pytest
from unittest.mock import patch

from autocrud.storage import MemoryStorage, DiskStorage


class TestMemoryStorageCoverage:
    """測試 MemoryStorage 的未覆蓋功能"""

    def test_memory_storage_clear(self):
        """測試 MemoryStorage.clear() 方法"""
        storage = MemoryStorage()

        # 添加一些數據
        storage.set("key1", "value1")
        storage.set("key2", "value2")

        # 確認數據存在
        assert storage.size() == 2
        assert storage.exists("key1")
        assert storage.exists("key2")

        # 清空數據
        storage.clear()

        # 確認數據已清空
        assert storage.size() == 0
        assert not storage.exists("key1")
        assert not storage.exists("key2")
        assert storage.list_keys() == []

    def test_memory_storage_size(self):
        """測試 MemoryStorage.size() 方法"""
        storage = MemoryStorage()

        # 空存儲
        assert storage.size() == 0

        # 添加數據
        storage.set("key1", "value1")
        assert storage.size() == 1

        storage.set("key2", "value2")
        assert storage.size() == 2

        # 刪除數據
        storage.delete("key1")
        assert storage.size() == 1

        storage.delete("key2")
        assert storage.size() == 0


class TestDiskStorageCoverage:
    """測試 DiskStorage 的未覆蓋功能"""

    def test_disk_storage_get_with_read_error(self):
        """測試 DiskStorage.get() 讀取文件時的異常處理"""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = DiskStorage(temp_dir)

            # 創建一個文件
            storage.set("test_key", {"data": "test"})

            # 模擬讀取文件時發生錯誤
            with patch("builtins.open", side_effect=IOError("讀取錯誤")):
                with patch("builtins.print") as mock_print:
                    result = storage.get("test_key")

                    # 應該返回 None 並打印錯誤
                    assert result is None
                    mock_print.assert_called_once()
                    assert "讀取文件失敗" in str(mock_print.call_args)

    def test_disk_storage_set_with_write_error(self):
        """測試 DiskStorage.set() 寫入文件時的異常處理"""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = DiskStorage(temp_dir)

            # 模擬寫入文件時發生錯誤
            with patch("builtins.open", side_effect=IOError("寫入錯誤")):
                with patch("builtins.print") as mock_print:
                    with pytest.raises(IOError):
                        storage.set("test_key", {"data": "test"})

                    # 應該打印錯誤並重新拋出異常
                    mock_print.assert_called_once()
                    assert "寫入文件失敗" in str(mock_print.call_args)

    def test_disk_storage_delete_with_error(self):
        """測試 DiskStorage.delete() 刪除文件時的異常處理"""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = DiskStorage(temp_dir)

            # 創建一個文件
            storage.set("test_key", {"data": "test"})

            # 模擬刪除文件時發生錯誤
            with patch("os.remove", side_effect=OSError("刪除錯誤")):
                with patch("builtins.print") as mock_print:
                    result = storage.delete("test_key")

                    # 應該返回 False 並打印錯誤
                    assert result is False
                    mock_print.assert_called_once()
                    assert "刪除文件失敗" in str(mock_print.call_args)

    def test_disk_storage_list_keys_with_error(self):
        """測試 DiskStorage.list_keys() 列出文件時的異常處理"""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = DiskStorage(temp_dir)

            # 創建一些文件
            storage.set("key1", "value1")
            storage.set("key2", "value2")

            # 模擬列出目錄時發生錯誤
            with patch("os.listdir", side_effect=OSError("列出錯誤")):
                with patch("builtins.print") as mock_print:
                    keys = storage.list_keys()

                    # 應該返回空列表並打印錯誤
                    assert keys == []
                    mock_print.assert_called_once()
                    assert "列出文件失敗" in str(mock_print.call_args)

    def test_disk_storage_clear(self):
        """測試 DiskStorage.clear() 方法"""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = DiskStorage(temp_dir)

            # 創建一些文件
            storage.set("key1", "value1")
            storage.set("key2", "value2")

            # 確認文件存在
            assert storage.exists("key1")
            assert storage.exists("key2")
            assert storage.size() == 2

            # 清空存儲
            storage.clear()

            # 確認文件已被刪除
            assert not storage.exists("key1")
            assert not storage.exists("key2")
            assert storage.size() == 0
            assert storage.list_keys() == []

    def test_disk_storage_clear_with_error(self):
        """測試 DiskStorage.clear() 清空時的異常處理"""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = DiskStorage(temp_dir)

            # 創建一些文件
            storage.set("key1", "value1")
            storage.set("key2", "value2")

            # 模擬列出目錄時發生錯誤
            with patch("os.listdir", side_effect=OSError("列出錯誤")):
                with patch("builtins.print") as mock_print:
                    storage.clear()

                    # 應該打印錯誤
                    mock_print.assert_called_once()
                    assert "清空目錄失敗" in str(mock_print.call_args)

    def test_disk_storage_size(self):
        """測試 DiskStorage.size() 方法"""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = DiskStorage(temp_dir)

            # 空存儲
            assert storage.size() == 0

            # 添加文件
            storage.set("key1", "value1")
            assert storage.size() == 1

            storage.set("key2", "value2")
            assert storage.size() == 2

            # 刪除文件
            storage.delete("key1")
            assert storage.size() == 1

            storage.delete("key2")
            assert storage.size() == 0

    def test_disk_storage_list_keys_with_non_data_files(self):
        """測試 DiskStorage.list_keys() 忽略非 .data 文件"""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = DiskStorage(temp_dir)

            # 創建 .data 文件（使用簡單的鍵名避免轉換問題）
            storage.set("validkey", "value")

            # 創建非 .data 文件
            non_data_file = os.path.join(temp_dir, "invalid.txt")
            with open(non_data_file, "w") as f:
                f.write("invalid content")

            # list_keys 應該只返回 .data 文件對應的鍵
            keys = storage.list_keys()
            assert "validkey" in keys
            assert len(keys) == 1  # 只有一個有效的 .data 文件
