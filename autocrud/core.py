"""AutoCRUD 核心模組"""

import uuid
from typing import Any, Dict, Type, Optional, TypeVar, Generic, List
from datetime import datetime
from .converter import ModelConverter
from .storage import Storage
from .updater import AdvancedUpdater
from .metadata import MetadataConfig
from .schema_analyzer import SchemaAnalyzer
from .list_params import ListQueryParams, ListResult, DateTimeRange, SortOrder

# 定義泛型類型變數
T = TypeVar("T")


class SingleModelCRUD(Generic[T]):
    """自動 CRUD 系統核心類"""

    def __init__(
        self,
        model: Type[T],
        storage: Storage,
        resource_name: str,
        id_generator: Optional[callable] = None,
        metadata_config: Optional[MetadataConfig] = None,
        default_values: Optional[Dict[str, Any]] = None,
    ):
        self.model = model
        self.storage = storage
        self.resource_name = resource_name
        self.converter = ModelConverter()
        self.id_generator = id_generator or (lambda: str(uuid.uuid4()))
        self.metadata_config = metadata_config or MetadataConfig()
        self.default_values = default_values or {}

        # 使用 schema 分析器，並傳遞 default_values
        self.schema_analyzer = SchemaAnalyzer(
            model, self.metadata_config, self.default_values
        )

        # 驗證模型類型（保持向後兼容）
        self.model_type = self.converter.detect_model_type(model)
        self.model_fields = self.converter.extract_fields(model)

    def _make_key(self, resource_id: str) -> str:
        """生成存儲鍵"""
        return f"{self.resource_name}:{resource_id}"

    def create(self, data: Dict[str, Any]) -> str:
        """創建資源，回傳資源 ID"""
        # 先合併預設值，但不覆蓋用戶提供的值
        merged_data = {**self.default_values, **data}

        # 應用 metadata（時間戳和用戶追蹤）
        enriched_data = self.schema_analyzer.prepare_create_data(merged_data)

        # 生成資源 ID
        resource_id = self.id_generator()

        # 設置 ID 欄位（用戶必須在模型中定義此欄位）
        id_field = self.schema_analyzer.get_id_field_name()
        enriched_data[id_field] = resource_id

        # 創建模型實例
        instance = self.converter.from_dict(self.model, enriched_data)

        # 轉換為字典
        instance_dict = self.converter.to_dict(instance)

        # 存儲
        key = self._make_key(resource_id)
        self.storage.set(key, instance_dict)

        return resource_id

    def get(self, resource_id: str) -> Optional[Dict[str, Any]]:
        """獲取資源"""
        key = self._make_key(resource_id)
        return self.storage.get(key)

    def update(self, resource_id: str, data: Dict[str, Any]) -> bool:
        """更新資源，回傳是否更新成功"""
        key = self._make_key(resource_id)

        # 檢查資源是否存在
        if not self.storage.exists(key):
            return False

        # 獲取現有資料
        existing_data = self.storage.get(key)
        if existing_data is None:
            return False

        # 合併現有資料和更新資料
        merged_data = existing_data.copy()
        merged_data.update(data)

        # 應用 metadata（更新時間戳和用戶追蹤）
        enriched_data = self.schema_analyzer.prepare_update_data(merged_data)

        # 保持 ID
        id_field = self.schema_analyzer.get_id_field_name()
        enriched_data[id_field] = resource_id

        # 創建模型實例驗證數據
        instance = self.converter.from_dict(self.model, enriched_data)

        # 轉換為字典
        instance_dict = self.converter.to_dict(instance)

        # 更新存儲
        self.storage.set(key, instance_dict)

        return True

    def advanced_update(
        self, resource_id: str, update_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """使用 Advanced Updater 進行細部更新"""
        key = self._make_key(resource_id)

        # 檢查資源是否存在
        if not self.storage.exists(key):
            return None

        # 獲取當前數據
        current_data = self.storage.get(key)
        if current_data is None:
            return None

        # 創建並應用 updater
        updater = AdvancedUpdater.from_dict(update_data)
        updated_data = updater.apply_to(current_data)

        # 應用 update metadata（更新時間戳和用戶追蹤）
        updated_data = self.schema_analyzer.prepare_update_data(updated_data)

        # 保持 ID 不變
        id_field = self.schema_analyzer.get_id_field_name()
        updated_data[id_field] = resource_id

        # 驗證更新後的數據
        try:
            instance = self.converter.from_dict(self.model, updated_data)
            instance_dict = self.converter.to_dict(instance)
        except Exception:
            # 如果數據驗證失敗，返回 None
            return None

        # 更新存儲
        self.storage.set(key, instance_dict)

        return instance_dict

    def delete(self, resource_id: str) -> bool:
        """刪除資源"""
        key = self._make_key(resource_id)
        return self.storage.delete(key)

    def exists(self, resource_id: str) -> bool:
        """檢查資源是否存在"""
        key = self._make_key(resource_id)
        return self.storage.exists(key)

    def list_all(
        self, params: Optional[ListQueryParams] = None
    ) -> List[Dict[str, Any]]:
        """列出所有資源（保持向後兼容）"""
        if params is None:
            # 向後兼容：返回所有資源的簡單列表
            return self._get_all_items()
        else:
            # 使用新的高級查詢
            result = self.list_with_params(params)
            return result.items

    def list_with_params(self, params: ListQueryParams) -> ListResult:
        """使用查詢參數列出資源"""
        # 獲取所有項目
        all_items = self._get_all_items()

        # 應用過濾器
        filtered_items = self._apply_filters(all_items, params)

        # 應用排序
        sorted_items = self._apply_sorting(filtered_items, params)

        # 計算總數
        total = len(sorted_items)

        # 應用分頁
        paginated_items = self._apply_pagination(sorted_items, params)

        return ListResult.create(paginated_items, total, params)

    def _get_all_items(self) -> List[Dict[str, Any]]:
        """獲取所有項目"""
        all_keys = self.storage.list_keys()
        result = []
        for key in all_keys:
            data = self.storage.get(key)
            if data:
                result.append(data)
        return result

    def _apply_filters(
        self, items: List[Dict[str, Any]], params: ListQueryParams
    ) -> List[Dict[str, Any]]:
        """應用過濾器"""
        if not items:
            return items

        filtered_items = items

        # 按創建者過濾
        if params.created_by_filter and self.metadata_config.enable_user_tracking:
            created_by_field = self.metadata_config.created_by_field
            filtered_items = [
                item
                for item in filtered_items
                if item.get(created_by_field) in params.created_by_filter
            ]

        # 按更新者過濾
        if params.updated_by_filter and self.metadata_config.enable_user_tracking:
            updated_by_field = self.metadata_config.updated_by_field
            filtered_items = [
                item
                for item in filtered_items
                if item.get(updated_by_field) in params.updated_by_filter
            ]

        # 按創建時間過濾
        if params.created_time_range and self.metadata_config.enable_timestamps:
            created_time_field = self.metadata_config.created_time_field
            filtered_items = [
                item
                for item in filtered_items
                if self._is_datetime_in_range(
                    item.get(created_time_field), params.created_time_range
                )
            ]

        # 按更新時間過濾
        if params.updated_time_range and self.metadata_config.enable_timestamps:
            updated_time_field = self.metadata_config.updated_time_field
            filtered_items = [
                item
                for item in filtered_items
                if self._is_datetime_in_range(
                    item.get(updated_time_field), params.updated_time_range
                )
            ]

        return filtered_items

    def _apply_sorting(
        self, items: List[Dict[str, Any]], params: ListQueryParams
    ) -> List[Dict[str, Any]]:
        """應用排序"""
        if not items or not params.sort_by:
            return items

        # 檢查排序字段是否有效
        valid_sort_fields = []
        if self.metadata_config.enable_timestamps:
            valid_sort_fields.extend(
                [
                    self.metadata_config.created_time_field,
                    self.metadata_config.updated_time_field,
                ]
            )
        if self.metadata_config.enable_user_tracking:
            valid_sort_fields.extend(
                [
                    self.metadata_config.created_by_field,
                    self.metadata_config.updated_by_field,
                ]
            )

        if params.sort_by not in valid_sort_fields:
            # 如果排序字段無效，返回原始列表
            return items

        # 執行排序
        reverse = params.sort_order == SortOrder.DESC
        try:
            return sorted(
                items, key=lambda x: x.get(params.sort_by) or "", reverse=reverse
            )
        except (TypeError, KeyError):
            # 如果排序失敗，返回原始列表
            return items

    def _apply_pagination(
        self, items: List[Dict[str, Any]], params: ListQueryParams
    ) -> List[Dict[str, Any]]:
        """應用分頁"""
        if not items:
            return items

        start_index = (params.page - 1) * params.page_size
        end_index = start_index + params.page_size

        return items[start_index:end_index]

    def _is_datetime_in_range(self, value: Any, date_range: DateTimeRange) -> bool:
        """檢查日期時間是否在範圍內"""
        if not value:
            return False

        # 如果值是字符串，嘗試解析為 datetime
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except (ValueError, AttributeError):
                return False
        elif not isinstance(value, datetime):
            return False

        # 處理時區不匹配問題：統一轉換到 local timezone
        from datetime import timezone

        # 獲取本地時區偏移
        local_tz = timezone(datetime.now().astimezone().utcoffset())

        # 如果 date_range 的 start/end 是 naive，假設為 local timezone
        start = date_range.start
        end = date_range.end

        if start and start.tzinfo is None:
            start = start.replace(tzinfo=local_tz)
        if end and end.tzinfo is None:
            end = end.replace(tzinfo=local_tz)

        # 如果 value 有時區信息，轉換到 local timezone；如果沒有，假設為 UTC 然後轉換
        if value.tzinfo is not None:
            value = value.astimezone(local_tz)
        else:
            # 系統存儲的時間戳沒有時區信息時，假設為 UTC
            value = value.replace(tzinfo=timezone.utc).astimezone(local_tz)

        # 創建臨時的 DateTimeRange 進行比較
        temp_range = DateTimeRange(start=start, end=end)
        return temp_range.contains(value)

    def count(self) -> int:
        """取得資源總數量"""
        all_keys = self.storage.list_keys()

        count = 0
        for key in all_keys:
            # 確認資料確實存在（不是空值）
            data = self.storage.get(key)
            if data:
                count += 1

        return count

    def create_fastapi_app(self, route_config=None, **kwargs):
        """創建 FastAPI 應用的便利方法"""
        from .fastapi_generator import FastAPIGenerator

        generator = FastAPIGenerator(self, route_config=route_config)
        return generator.create_fastapi_app(**kwargs)


# 使用範例
if __name__ == "__main__":
    from dataclasses import dataclass
    from .storage import MemoryStorage

    @dataclass
    class User:
        name: str
        email: str
        age: int

    # 創建 AutoCRUD 實例
    storage = MemoryStorage()
    crud = SingleModelCRUD(model=User, storage=storage, resource_name="users")

    # 測試創建
    user_data = {"name": "Alice", "email": "alice@example.com", "age": 30}
    created_user = crud.create(user_data)
    print(f"創建用戶: {created_user}")

    # 測試獲取
    user_id = created_user["id"]
    retrieved_user = crud.get(user_id)
    print(f"獲取用戶: {retrieved_user}")

    # 測試更新
    updated_data = {
        "name": "Alice Smith",
        "email": "alice.smith@example.com",
        "age": 31,
    }
    updated_user = crud.update(user_id, updated_data)
    print(f"更新用戶: {updated_user}")

    # 測試列出所有
    all_users = crud.list_all()
    print(f"所有用戶: {all_users}")

    # 測試刪除
    deleted = crud.delete(user_id)
    print(f"刪除成功: {deleted}")
    print(f"刪除後存在: {crud.exists(user_id)}")
