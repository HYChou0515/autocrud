"""提升 core.py 覆蓋率的測試（簡化版本）"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from unittest.mock import patch

from autocrud.core import SingleModelCRUD
from autocrud.storage import MemoryStorage
from autocrud.metadata import MetadataConfig
from autocrud.list_params import ListQueryParams, DateTimeRange


@dataclass
class CoreTestModel:
    """測試用的資料模型"""

    id: str
    name: str
    age: int
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None


class TestSingleModelCRUDCoverage:
    """測試 SingleModelCRUD 的未覆蓋功能"""

    def test_update_nonexistent_item(self):
        """測試更新不存在的項目 - 覆蓋第 87 行"""
        storage = MemoryStorage()
        metadata_config = MetadataConfig(enable_timestamps=True)
        crud = SingleModelCRUD(
            CoreTestModel, storage, "test_model", metadata_config=metadata_config
        )

        # 嘗試更新不存在的項目，應該返回 False
        result = crud.update("nonexistent", {"name": "updated"})
        assert result is False

    def test_advanced_update_nonexistent_item(self):
        """測試高級更新不存在的項目 - 覆蓋第 122 行"""
        storage = MemoryStorage()
        metadata_config = MetadataConfig(enable_timestamps=True)
        crud = SingleModelCRUD(
            CoreTestModel, storage, "test_model", metadata_config=metadata_config
        )

        # 嘗試高級更新不存在的項目，應該返回 None
        result = crud.advanced_update("nonexistent", {"name": "updated"})
        assert result is None

    def test_advanced_update_with_validation_failure(self):
        """測試高級更新時數據驗證失敗 - 覆蓋第 147-149 行"""
        storage = MemoryStorage()
        metadata_config = MetadataConfig(enable_timestamps=True)
        crud = SingleModelCRUD(
            CoreTestModel, storage, "test_model", metadata_config=metadata_config
        )

        # 先創建一個項目
        original_data = {"id": "test1", "name": "Test", "age": 25}
        created_id = crud.create(original_data)

        # 模擬 converter.from_dict 拋出異常（數據驗證失敗）
        with patch.object(
            crud.converter, "from_dict", side_effect=ValueError("Invalid data")
        ):
            result = crud.advanced_update(created_id, {"age": "invalid"})
            assert result is None

    def test_sort_with_invalid_field(self):
        """測試使用無效欄位排序 - 覆蓋排序邏輯中的異常分支"""
        storage = MemoryStorage()
        metadata_config = MetadataConfig()
        crud = SingleModelCRUD(
            CoreTestModel, storage, "test_model", metadata_config=metadata_config
        )

        # 創建測試數據
        crud.create({"id": "1", "name": "Alice", "age": 30})
        crud.create({"id": "2", "name": "Bob", "age": 25})

        # 使用無效欄位排序，應該返回原始列表
        params = ListQueryParams(sort_by="invalid_field")
        result = crud.list_all(params)  # 返回的是 list，不是 ListResult

        # 應該返回所有項目
        assert len(result) == 2

    def test_count_method(self):
        """測試 count 方法 - 覆蓋 count 方法"""
        storage = MemoryStorage()
        metadata_config = MetadataConfig()
        crud = SingleModelCRUD(
            CoreTestModel, storage, "test_model", metadata_config=metadata_config
        )

        # 初始計數應該為 0
        assert crud.count() == 0

        # 創建一些項目
        crud.create({"id": "1", "name": "Alice", "age": 30})
        id2 = crud.create({"id": "2", "name": "Bob", "age": 25})
        crud.create({"id": "3", "name": "Charlie", "age": 35})

        # 計數應該為 3
        assert crud.count() == 3

        # 刪除一個項目（使用創建時返回的ID）
        result = crud.delete(id2)
        assert result is True

        # 計數應該為 2
        assert crud.count() == 2

    def test_create_fastapi_app_convenience_method(self):
        """測試創建 FastAPI 應用的便利方法"""
        storage = MemoryStorage()
        metadata_config = MetadataConfig()
        crud = SingleModelCRUD(
            CoreTestModel, storage, "test_model", metadata_config=metadata_config
        )

        # 測試便利方法
        app = crud.create_fastapi_app()

        # 驗證返回的是 FastAPI 應用實例
        from fastapi import FastAPI

        assert isinstance(app, FastAPI)

    def test_empty_list_pagination(self):
        """測試空列表的分頁處理"""
        storage = MemoryStorage()
        metadata_config = MetadataConfig()
        crud = SingleModelCRUD(
            CoreTestModel, storage, "test_model", metadata_config=metadata_config
        )

        # 對空列表進行分頁查詢
        params = ListQueryParams(page=10, page_size=5)
        result = crud.list_with_params(params)

        # 應該返回空結果
        assert len(result.items) == 0
        assert result.total == 0
        assert result.page == 10
        assert result.page_size == 5

    def test_sort_with_none_values(self):
        """測試排序時處理 None 值"""
        storage = MemoryStorage()
        metadata_config = MetadataConfig()
        crud = SingleModelCRUD(
            CoreTestModel, storage, "test_model", metadata_config=metadata_config
        )

        # 創建測試數據
        crud.create({"id": "1", "name": "Alice", "age": 30})
        id2 = crud.create({"id": "2", "name": "Bob", "age": 25})

        # 手動設置一個項目的 name 為 None
        key = f"test_model:{id2}"
        data = storage.get(key)
        if data:
            data["name"] = None
            storage.set(key, data)

        # 按 name 排序
        params = ListQueryParams(sort_by="name")
        result = crud.list_with_params(params)

        # 應該能正常排序
        assert len(result.items) == 2

    def test_advanced_update_success_path(self):
        """測試高級更新成功路徑 - 確保正常功能也被覆蓋"""
        storage = MemoryStorage()
        metadata_config = MetadataConfig(enable_timestamps=True)
        crud = SingleModelCRUD(
            CoreTestModel, storage, "test_model", metadata_config=metadata_config
        )

        # 創建初始數據
        initial_data = {"name": "Test", "age": 25}
        created_id = crud.create(initial_data)

        # 執行高級更新操作
        update_operations = {"name": "Updated Test"}
        result = crud.advanced_update(created_id, update_operations)

        # 驗證更新成功
        assert result is not None
        assert result["name"] == "Updated Test"
        assert result["age"] == 25
        assert result["id"] == created_id

    def test_coverage_imports(self):
        """測試導入相關的覆蓋率"""
        from autocrud.core import SingleModelCRUD
        from autocrud.storage import MemoryStorage

        # 驗證我們可以正常創建實例
        storage = MemoryStorage()
        crud = SingleModelCRUD(CoreTestModel, storage, "test_model")
        assert crud is not None

    def test_datetime_filter_edge_cases(self):
        """測試日期時間過濾的邊緣情況"""
        storage = MemoryStorage()
        metadata_config = MetadataConfig(enable_timestamps=True)
        crud = SingleModelCRUD(
            CoreTestModel, storage, "test_model", metadata_config=metadata_config
        )

        # 創建測試數據
        created_id = crud.create({"id": "1", "name": "Test", "age": 30})
        key = f"test_model:{created_id}"
        data = storage.get(key)

        # 測試無效字符串格式
        if data:
            data["created_time"] = "invalid-datetime-format"
            storage.set(key, data)

            params = ListQueryParams(
                created_time_range=DateTimeRange(
                    start=datetime(2023, 1, 1), end=datetime(2023, 12, 31)
                )
            )
            result = crud.list_with_params(params)
            # 由於時間格式無效，項目應該被過濾掉
            assert len(result.items) == 0

        # 測試非字符串非日期時間類型
        if data:
            data["created_time"] = 12345  # 數字
            storage.set(key, data)

            result = crud.list_with_params(params)
            # 由於時間戳類型無效，項目應該被過濾掉
            assert len(result.items) == 0

    def test_list_backward_compatibility(self):
        """測試 list_all 的向後兼容性"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(CoreTestModel, storage, "test_model")

        # 創建測試數據
        crud.create({"id": "1", "name": "Alice", "age": 30})
        crud.create({"id": "2", "name": "Bob", "age": 25})

        # 不帶參數的 list_all 應該返回所有項目
        result = crud.list_all()
        assert len(result) == 2

        # 帶參數的 list_all 應該返回過濾後的項目列表
        params = ListQueryParams(page=1, page_size=1)
        result_with_params = crud.list_all(params)
        assert len(result_with_params) == 1
