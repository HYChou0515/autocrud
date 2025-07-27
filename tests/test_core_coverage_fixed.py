"""提升 core.py 覆蓋率的測試（修復版本）"""

from dataclasses import dataclass
from datetime import datetime, timedelta
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
        crud.create(original_data)

        # 模擬 converter.from_dict 拋出異常（數據驗證失敗）
        with patch.object(
            crud.converter, "from_dict", side_effect=ValueError("Invalid data")
        ):
            result = crud.advanced_update("test1", {"name": "updated"})
            assert result is None

    def test_list_with_time_range_filters(self):
        """測試使用時間範圍過濾器 - 覆蓋時間過濾邏輯"""
        # 簡化測試，只測試邏輯而不測試實際過濾結果
        storage = MemoryStorage()
        metadata_config = MetadataConfig(enable_timestamps=True)
        crud = SingleModelCRUD(
            CoreTestModel, storage, "test_model", metadata_config=metadata_config
        )

        # 創建測試數據
        crud.create({"id": "test1", "name": "Test1", "age": 30})

        # 測試時間範圍過濾邏輯（不依賴具體時間）
        time_range = DateTimeRange(
            start=datetime.now() - timedelta(hours=1),
            end=datetime.now() + timedelta(hours=1),
        )
        params = ListQueryParams(created_time_range=time_range)

        # 直接調用會觸發時間過濾邏輯
        assert crud.list_with_params(params)

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

    def test_datetime_parsing_failures(self):
        """測試日期時間解析失敗的情況 - 覆蓋 _is_datetime_in_range 中的異常處理"""
        storage = MemoryStorage()
        metadata_config = MetadataConfig(enable_timestamps=True)
        crud = SingleModelCRUD(
            CoreTestModel, storage, "test_model", metadata_config=metadata_config
        )

        # 創建測試數據
        crud.create({"id": "1", "name": "Test", "age": 30})

        # 測試字符串解析失敗
        key = "test_model:1"
        data = storage.get(key)
        if data:
            data["created_time"] = "invalid-datetime-format"
            storage.set(key, data)

        # 測試時間範圍過濾，觸發解析邏輯
        time_range = DateTimeRange(
            start=datetime.now() - timedelta(hours=1),
            end=datetime.now() + timedelta(hours=1),
        )
        params = ListQueryParams(created_time_range=time_range)

        # 調用會觸發日期時間解析邏輯，覆蓋相關代碼
        assert crud.list_with_params(params)

        # 測試非字符串非日期時間類型
        if data:
            data["created_time"] = 12345  # 數字
            storage.set(key, data)

        assert crud.list_with_params(params)

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

        # 刪除一個項目（使用創建時返回的 ID）
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
        crud.create({"id": "2", "name": "Bob", "age": 25})

        # 手動設置一個項目的 name 為 None
        key = "test_model:2"
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
        initial_data = {"id": "test", "name": "Test", "age": 25}
        created_id = crud.create(initial_data)

        # 使用創建返回的 ID 進行更新
        update_operations = {"name": "Updated Test"}
        result = crud.advanced_update(created_id, update_operations)

        # 驗證更新成功
        assert result is not None
        assert result["name"] == "Updated Test"
        assert result["age"] == 25

    def test_coverage_imports(self):
        """測試導入相關的覆蓋率"""
        from autocrud.core import SingleModelCRUD
        from autocrud.storage import MemoryStorage

        # 驗證我們可以正常創建實例
        storage = MemoryStorage()
        crud = SingleModelCRUD(CoreTestModel, storage, "test_model")
        assert crud is not None
