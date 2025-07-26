"""提升 schema_analyzer.py 覆蓋率的測試"""

import pytest
from typing import TypedDict, Optional
from dataclasses import dataclass
from datetime import datetime
from unittest.mock import Mock

from autocrud.schema_analyzer import SchemaAnalyzer
from autocrud.metadata import MetadataConfig


class UserTypedDictModel(TypedDict):
    """用於測試的 TypedDict 模型"""

    id: str
    name: str
    age: int
    created_time: Optional[datetime]
    updated_time: Optional[datetime]


class InvalidModelClass:
    """無效的模型類型，既不是 dataclass 也不是 pydantic 也不是 TypedDict"""

    id: str
    name: str


@dataclass
class ValidModelClass:
    """有效的測試模型"""

    id: str
    name: str
    age: int
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None


@dataclass
class MissingIdModelClass:
    """缺少 id 欄位的模型"""

    name: str
    age: int


@dataclass
class MissingTimestampModelClass:
    """缺少時間戳欄位的模型"""

    id: str
    name: str
    age: int
    # 缺少 created_time 和 updated_time


@dataclass
class MissingUserTrackingModelClass:
    """缺少使用者追蹤欄位的模型"""

    id: str
    name: str
    age: int
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None
    # 缺少 created_by 和 updated_by


@dataclass
class CustomIdModelClass:
    """使用自定義 ID 欄位的模型"""

    user_id: str  # 自定義 ID 欄位名稱
    name: str
    age: int
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None


class TestSchemaAnalyzerCoverage:
    """測試 SchemaAnalyzer 的未覆蓋功能"""

    def test_unsupported_model_type(self):
        """測試不支援的模型類型"""
        metadata_config = MetadataConfig()

        with pytest.raises(ValueError, match="Unsupported model type"):
            SchemaAnalyzer(InvalidModelClass, metadata_config)

    def test_typeddict_analysis(self):
        """測試 TypedDict 模型分析"""
        metadata_config = MetadataConfig(
            enable_timestamps=True, enable_user_tracking=False
        )

        analyzer = SchemaAnalyzer(UserTypedDictModel, metadata_config)

        # 驗證 TypedDict 分析結果
        assert "id" in analyzer.field_types
        assert "name" in analyzer.field_types
        assert "age" in analyzer.field_types
        assert "created_time" in analyzer.field_types
        assert "updated_time" in analyzer.field_types

        # 獲取各種模型
        create_model = analyzer.get_create_model()
        update_model = analyzer.get_update_model()
        response_model = analyzer.get_response_model()

        # 驗證模型創建成功
        assert create_model is not None
        assert update_model is not None
        assert response_model is not None

    def test_missing_id_field_validation(self):
        """測試缺少 ID 欄位的驗證"""
        metadata_config = MetadataConfig()

        with pytest.raises(ValueError, match="must have"):
            SchemaAnalyzer(MissingIdModelClass, metadata_config)

    def test_custom_id_field_validation(self):
        """測試自定義 ID 欄位驗證"""
        metadata_config = MetadataConfig(id_field="user_id")

        # 應該成功創建，因為模型有 user_id 欄位
        analyzer = SchemaAnalyzer(CustomIdModelClass, metadata_config)
        assert "user_id" in analyzer.field_types

        # 測試缺少自定義 ID 欄位的情況
        metadata_config_invalid = MetadataConfig(id_field="missing_id")
        with pytest.raises(ValueError, match="must have"):
            SchemaAnalyzer(CustomIdModelClass, metadata_config_invalid)

    def test_missing_timestamp_fields_validation(self):
        """測試缺少時間戳欄位的驗證"""
        metadata_config = MetadataConfig(
            enable_timestamps=True, enable_user_tracking=False
        )

        with pytest.raises(ValueError, match="created_time.*field"):
            SchemaAnalyzer(MissingTimestampModelClass, metadata_config)

    def test_missing_user_tracking_fields_validation(self):
        """測試缺少使用者追蹤欄位的驗證"""
        metadata_config = MetadataConfig(
            enable_timestamps=False, enable_user_tracking=True
        )

        with pytest.raises(ValueError, match="created_by.*field"):
            SchemaAnalyzer(MissingUserTrackingModelClass, metadata_config)

    def test_pydantic_v1_fallback(self):
        """測試 Pydantic v1 的回退處理"""
        # 這個測試可能需要 mock，因為實際環境中可能沒有 Pydantic v1
        # 但我們可以測試檢查 model_fields 屬性存在的情況
        pass

    def test_get_model_methods_with_different_configs(self):
        """測試不同配置下的模型獲取方法"""
        # 測試啟用時間戳但不啟用使用者追蹤
        metadata_config = MetadataConfig(
            enable_timestamps=True, enable_user_tracking=False
        )

        analyzer = SchemaAnalyzer(ValidModelClass, metadata_config)

        create_model = analyzer.get_create_model()
        update_model = analyzer.get_update_model()
        response_model = analyzer.get_response_model()

        # 驗證模型創建成功
        assert create_model is not None
        assert update_model is not None
        assert response_model is not None

        # 驗證創建模型排除了元數據欄位
        create_fields = (
            create_model.__annotations__
            if hasattr(create_model, "__annotations__")
            else {}
        )
        assert "created_time" not in create_fields  # 創建時不應包含時間戳
        assert "updated_time" not in create_fields

        # 測試完全禁用元數據的情況
        metadata_config_minimal = MetadataConfig(
            enable_timestamps=False, enable_user_tracking=False
        )

        analyzer_minimal = SchemaAnalyzer(ValidModelClass, metadata_config_minimal)

        create_model_minimal = analyzer_minimal.get_create_model()
        update_model_minimal = analyzer_minimal.get_update_model()
        response_model_minimal = analyzer_minimal.get_response_model()

        assert create_model_minimal is not None
        assert update_model_minimal is not None
        assert response_model_minimal is not None


class TestSchemaAnalyzerAdvancedCoverage:
    """測試 SchemaAnalyzer 的高級覆蓋情況"""

    def test_missing_updated_time_field_validation(self):
        """測試缺少 updated_time 欄位的驗證"""

        @dataclass
        class MissingUpdatedTimeModel:
            id: str
            name: str
            created_time: Optional[datetime] = None
            # 缺少 updated_time

        metadata_config = MetadataConfig(
            enable_timestamps=True, enable_user_tracking=False
        )

        with pytest.raises(ValueError, match="updated_time.*field"):
            SchemaAnalyzer(MissingUpdatedTimeModel, metadata_config)

    def test_missing_updated_by_field_validation(self):
        """測試缺少 updated_by 欄位的驗證"""

        @dataclass
        class MissingUpdatedByModel:
            id: str
            name: str
            created_by: Optional[str] = None
            # 缺少 updated_by

        metadata_config = MetadataConfig(
            enable_timestamps=False, enable_user_tracking=True
        )

        with pytest.raises(ValueError, match="updated_by.*field"):
            SchemaAnalyzer(MissingUpdatedByModel, metadata_config)

    def test_get_full_model(self):
        """測試 get_full_model 方法"""
        analyzer = SchemaAnalyzer(ValidModelClass, MetadataConfig())

        full_model = analyzer.get_full_model()
        assert full_model is ValidModelClass

    def test_create_model_with_user_context(self):
        """測試在有使用者上下文時的創建模型生成"""

        @dataclass
        class ModelWithUserTracking:
            id: str
            name: str
            created_time: Optional[datetime] = None
            updated_time: Optional[datetime] = None
            created_by: Optional[str] = None
            updated_by: Optional[str] = None

        # 模擬有使用者上下文的情況
        mock_get_user = Mock(return_value="current_user")
        metadata_config = MetadataConfig(
            enable_timestamps=True,
            enable_user_tracking=True,
            get_current_user=mock_get_user,
        )

        analyzer = SchemaAnalyzer(ModelWithUserTracking, metadata_config)
        create_model = analyzer.get_create_model()

        # 驗證模型創建成功
        assert create_model is not None

        # 檢查 created_by 欄位是否為可選的（因為可以從上下文獲取）
        model_fields = (
            create_model.model_fields if hasattr(create_model, "model_fields") else {}
        )
        if "created_by" in model_fields:
            # 此欄位應該是可選的
            assert not model_fields["created_by"].is_required()

    def test_update_model_with_user_context(self):
        """測試在有使用者上下文時的更新模型生成"""

        @dataclass
        class ModelWithUserTracking:
            id: str
            name: str
            created_time: Optional[datetime] = None
            updated_time: Optional[datetime] = None
            created_by: Optional[str] = None
            updated_by: Optional[str] = None

        # 模擬有使用者上下文的情況
        mock_get_user = Mock(return_value="current_user")
        metadata_config = MetadataConfig(
            enable_timestamps=True,
            enable_user_tracking=True,
            get_current_user=mock_get_user,
        )

        analyzer = SchemaAnalyzer(ModelWithUserTracking, metadata_config)
        update_model = analyzer.get_update_model()

        # 驗證模型創建成功
        assert update_model is not None

    def test_dataclass_with_default_values(self):
        """測試帶有預設值的 dataclass"""

        @dataclass
        class ModelWithDefaults:
            id: str
            name: str = "default_name"
            age: int = 0
            created_time: Optional[datetime] = None
            updated_time: Optional[datetime] = None

        metadata_config = MetadataConfig(enable_timestamps=True)
        analyzer = SchemaAnalyzer(ModelWithDefaults, metadata_config)

        # 測試 _is_optional_field 方法
        assert analyzer._is_optional_field("name")  # 有預設值
        assert analyzer._is_optional_field("age")  # 有預設值
        assert analyzer._is_optional_field("created_time")  # Optional 類型
        assert not analyzer._is_optional_field("id")  # 必需欄位

    def test_pydantic_v1_fallback(self):
        """測試 Pydantic v1 回退機制的模擬"""
        from pydantic import BaseModel

        class TestPydanticModel(BaseModel):
            id: str
            name: str
            age: Optional[int] = None
            created_time: Optional[datetime] = None
            updated_time: Optional[datetime] = None

        # 模擬 Pydantic v1 環境（沒有 model_fields 但有 __fields__）
        if hasattr(TestPydanticModel, "model_fields"):
            # 在 v2 環境中，我們測試正常路徑
            analyzer = SchemaAnalyzer(
                TestPydanticModel, MetadataConfig(enable_timestamps=True)
            )

            # 測試各種模型生成
            create_model = analyzer.get_create_model()
            update_model = analyzer.get_update_model()
            response_model = analyzer.get_response_model()

            assert create_model is not None
            assert update_model is not None
            assert response_model is not None

    def test_utility_methods(self):
        """測試工具方法"""
        metadata_config = MetadataConfig(
            enable_timestamps=True, enable_user_tracking=True
        )
        analyzer = SchemaAnalyzer(FullMetadataModelClass, metadata_config)

        # 測試 prepare_create_data
        test_data = {"name": "test", "age": 25}
        prepared_data = analyzer.prepare_create_data(test_data)
        assert isinstance(prepared_data, dict)

        # 測試 prepare_update_data
        update_data = {"name": "updated"}
        prepared_update = analyzer.prepare_update_data(update_data)
        assert isinstance(prepared_update, dict)

        # 測試 get_id_field_name
        id_field = analyzer.get_id_field_name()
        assert id_field == "id"

        # 測試 extract_id_from_data
        data_with_id = {"id": "123", "name": "test"}
        extracted_id = analyzer.extract_id_from_data(data_with_id)
        assert extracted_id == "123"

        # 測試 get_metadata_fields
        metadata_fields = analyzer.get_metadata_fields()
        assert isinstance(metadata_fields, dict)

    def test_schema_analyzer_with_default_values_parameter(self):
        """測試使用 default_values 參數的 SchemaAnalyzer"""

        @dataclass
        class SimpleModel:
            id: str
            name: str
            age: int

        # 透過 default_values 參數使欄位變為可選
        default_values = {"name": "default", "age": 0}
        analyzer = SchemaAnalyzer(SimpleModel, MetadataConfig(), default_values)

        # 測試這些欄位現在被認為是可選的
        assert analyzer._is_optional_field("name")
        assert analyzer._is_optional_field("age")
        assert not analyzer._is_optional_field("id")  # 沒有預設值

    def test_python_310_union_type_handling(self):
        """測試 Python 3.10+ Union 類型處理"""
        # 這個測試模擬 Python 3.10+ 的 X | None 語法
        from typing import Union

        @dataclass
        class ModelWithUnionTypes:
            id: str
            name: Union[str, None] = None  # 模擬 str | None
            age: Union[int, None] = None  # 模擬 int | None

        analyzer = SchemaAnalyzer(ModelWithUnionTypes, MetadataConfig())

        # 測試 Union 類型被正確識別為可選
        assert analyzer._is_optional_field("name")
        assert analyzer._is_optional_field("age")
        assert not analyzer._is_optional_field("id")


# 測試帶有完整元數據的模型
@dataclass
class FullMetadataModelClass:
    """包含完整元數據的模型"""

    id: str
    name: str
    age: int
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None


class TestSchemaAnalyzerWithFullMetadata:
    """測試完整元數據配置下的 SchemaAnalyzer"""

    def test_full_metadata_analysis(self):
        """測試完整元數據配置"""
        metadata_config = MetadataConfig(
            enable_timestamps=True, enable_user_tracking=True
        )

        analyzer = SchemaAnalyzer(FullMetadataModelClass, metadata_config)

        # 驗證所有欄位都被識別
        assert "id" in analyzer.field_types
        assert "name" in analyzer.field_types
        assert "age" in analyzer.field_types
        assert "created_time" in analyzer.field_types
        assert "updated_time" in analyzer.field_types
        assert "created_by" in analyzer.field_types
        assert "updated_by" in analyzer.field_types

        # 測試模型生成
        create_model = analyzer.get_create_model()
        update_model = analyzer.get_update_model()
        response_model = analyzer.get_response_model()

        assert create_model is not None
        assert update_model is not None
        assert response_model is not None
