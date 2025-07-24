"""
測試 Schema 驗證功能
"""

import pytest
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

from autocrud import SingleModelCRUD, MemoryStorage, MetadataConfig
from autocrud.schema_analyzer import SchemaAnalyzer


@dataclass
class ValidUserModel:
    """包含所有必需欄位的有效用戶模型"""

    id: Optional[str] = None
    name: str = ""
    email: str = ""
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None


@dataclass
class InvalidUserModel:
    """缺少 ID 欄位的無效用戶模型"""

    name: str = ""
    email: str = ""


@dataclass
class NoTimestampModel:
    """有 ID 但缺少時間戳欄位的模型"""

    id: Optional[str] = None
    name: str = ""
    email: str = ""


class TestSchemaValidation:
    """測試 Schema 驗證功能"""

    def test_valid_model_passes_validation(self):
        """測試有效模型通過驗證"""
        # 這應該不會拋出異常
        analyzer = SchemaAnalyzer(ValidUserModel)
        assert analyzer.get_id_field_name() == "id"

    def test_missing_id_field_raises_error(self):
        """測試缺少 ID 欄位時拋出錯誤"""
        with pytest.raises(ValueError, match="must have an 'id' field"):
            SchemaAnalyzer(InvalidUserModel)

    def test_custom_id_field_validation(self):
        """測試自定義 ID 欄位驗證"""

        @dataclass
        class CustomIdModel:
            pk: Optional[str] = None
            name: str = ""

        # 使用自定義 ID 欄位名稱
        config = MetadataConfig(
            id_field="pk", enable_timestamps=False, enable_user_tracking=False
        )

        # 這應該不會拋出異常
        analyzer = SchemaAnalyzer(CustomIdModel, config)
        assert analyzer.get_id_field_name() == "pk"

    def test_custom_id_field_missing_raises_error(self):
        """測試自定義 ID 欄位不存在時拋出錯誤"""
        config = MetadataConfig(
            id_field="pk", enable_timestamps=False, enable_user_tracking=False
        )

        with pytest.raises(ValueError, match="must have a.*pk.*field"):
            SchemaAnalyzer(InvalidUserModel, config)

    def test_missing_timestamp_fields_raises_error(self):
        """測試缺少時間戳欄位時拋出錯誤"""
        # 啟用時間戳但模型缺少相關欄位
        config = MetadataConfig(enable_timestamps=True, enable_user_tracking=False)

        with pytest.raises(ValueError, match="must have a 'created_time' field"):
            SchemaAnalyzer(NoTimestampModel, config)

    def test_missing_user_tracking_fields_raises_error(self):
        """測試缺少用戶追蹤欄位時拋出錯誤"""
        # 啟用用戶追蹤但模型缺少相關欄位
        config = MetadataConfig(enable_timestamps=False, enable_user_tracking=True)

        with pytest.raises(ValueError, match="must have a 'created_by' field"):
            SchemaAnalyzer(NoTimestampModel, config)

    def test_crud_with_invalid_model_raises_error(self):
        """測試使用無效模型創建 CRUD 時拋出錯誤"""
        storage = MemoryStorage()

        with pytest.raises(ValueError, match="must have an 'id' field"):
            SingleModelCRUD(InvalidUserModel, storage, "users")

    def test_crud_with_valid_model_works(self):
        """測試使用有效模型創建 CRUD 正常工作"""
        storage = MemoryStorage()

        # 啟用時間戳和用戶追蹤
        config = MetadataConfig(enable_timestamps=True, enable_user_tracking=True)

        # 這應該不會拋出異常
        crud = SingleModelCRUD(ValidUserModel, storage, "users", metadata_config=config)

        # 測試創建操作
        user_data = {"name": "John", "email": "john@example.com"}
        user_id = crud.create(user_data)
        assert isinstance(user_id, str)

        # 驗證創建成功
        created_user = crud.get(user_id)
        assert created_user is not None
        assert created_user["name"] == "John"
        assert created_user["email"] == "john@example.com"
        assert created_user["id"] is not None
        assert created_user["created_time"] is not None
        assert created_user["updated_time"] is not None
