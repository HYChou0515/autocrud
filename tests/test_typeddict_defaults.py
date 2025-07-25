"""測試 TypedDict 與預設值的 register_model 功能"""

from typing import TypedDict
from autocrud import AutoCRUD
from autocrud.metadata import MetadataConfig


class SimpleTypedDict(TypedDict):
    id: str
    name: str
    email: str
    age: int
    status: str


class TestTypedDictDefaults:
    """測試 TypedDict 模型與 default_values 參數的功能"""

    def test_register_typeddict_with_defaults(self):
        """測試註冊 TypedDict 模型時提供預設值"""
        autocrud = AutoCRUD()

        # 註冊模型並提供預設值
        crud = autocrud.register_model(
            SimpleTypedDict, default_values={"status": "active", "age": 18}
        )

        # 驗證 SchemaAnalyzer 正確識別預設值欄位為 optional
        assert crud.schema_analyzer._is_optional_field("status")
        assert crud.schema_analyzer._is_optional_field("age")
        assert not crud.schema_analyzer._is_optional_field("name")
        assert not crud.schema_analyzer._is_optional_field("email")

    def test_create_with_defaults_applied(self):
        """測試創建時預設值被正確應用"""
        autocrud = AutoCRUD()

        autocrud.register_model(
            SimpleTypedDict, default_values={"status": "active", "age": 18}
        )

        # 創建時不提供有預設值的欄位
        user_id = autocrud.create(
            "simple_typed_dicts", {"name": "John Doe", "email": "john@example.com"}
        )

        user = autocrud.get("simple_typed_dicts", user_id)

        # 驗證預設值被應用
        assert user["status"] == "active"
        assert user["age"] == 18
        assert user["name"] == "John Doe"
        assert user["email"] == "john@example.com"

    def test_create_with_defaults_overridden(self):
        """測試創建時覆蓋預設值"""
        autocrud = AutoCRUD()

        autocrud.register_model(
            SimpleTypedDict, default_values={"status": "active", "age": 18}
        )

        # 創建時覆蓋預設值
        user_id = autocrud.create(
            "simple_typed_dicts",
            {
                "name": "Jane Doe",
                "email": "jane@example.com",
                "age": 25,  # 覆蓋預設值
                "status": "inactive",  # 覆蓋預設值
            },
        )

        user = autocrud.get("simple_typed_dicts", user_id)

        # 驗證覆蓋值被使用
        assert user["status"] == "inactive"
        assert user["age"] == 25
        assert user["name"] == "Jane Doe"
        assert user["email"] == "jane@example.com"

    def test_schema_models_reflect_defaults(self):
        """測試生成的 schema models 正確反映預設值"""
        autocrud = AutoCRUD()

        crud = autocrud.register_model(
            SimpleTypedDict, default_values={"status": "active", "age": 18}
        )

        # 取得 create model
        create_model = crud.schema_analyzer.get_create_model()

        # 檢查欄位的必填狀態
        if hasattr(create_model, "model_fields"):
            # Pydantic v2
            fields_info = create_model.model_fields

            # 有預設值的欄位應該不是必填的
            assert not fields_info["status"].is_required()
            assert not fields_info["age"].is_required()

            # 沒有預設值的欄位應該是必填的
            assert fields_info["name"].is_required()
            assert fields_info["email"].is_required()

            # ID 欄位不應該出現在 create model 中
            assert "id" not in fields_info

    def test_empty_defaults_dict(self):
        """測試空的預設值字典"""
        autocrud = AutoCRUD()

        crud = autocrud.register_model(SimpleTypedDict, default_values={})

        # 所有欄位都應該不是 optional（除了真正 optional 的類型）
        assert not crud.schema_analyzer._is_optional_field("status")
        assert not crud.schema_analyzer._is_optional_field("age")
        assert not crud.schema_analyzer._is_optional_field("name")
        assert not crud.schema_analyzer._is_optional_field("email")

    def test_none_defaults(self):
        """測試 None 作為預設值"""
        autocrud = AutoCRUD()

        crud = autocrud.register_model(SimpleTypedDict, default_values=None)

        # 行為應該與不提供 default_values 相同
        assert not crud.schema_analyzer._is_optional_field("status")
        assert not crud.schema_analyzer._is_optional_field("age")

    def test_defaults_with_metadata_config(self):
        """測試預設值與 metadata 配置結合使用"""
        autocrud = AutoCRUD()

        metadata_config = MetadataConfig(
            enable_timestamps=False, enable_user_tracking=False
        )

        autocrud.register_model(
            SimpleTypedDict,
            metadata_config=metadata_config,
            default_values={"status": "active", "age": 18},
        )

        # 驗證功能正常
        user_id = autocrud.create(
            "simple_typed_dicts", {"name": "Test User", "email": "test@example.com"}
        )

        user = autocrud.get("simple_typed_dicts", user_id)
        assert user["status"] == "active"
        assert user["age"] == 18
