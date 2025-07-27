"""測試數據類型轉換器和序列化器"""

import pytest
from autocrud import ModelConverter, SerializerFactory, MemoryStorage, SingleModelCRUD
from .test_models import DataclassUser, PydanticUser
import importlib.util

# 檢查 pydantic 是否可用
HAS_PYDANTIC = PydanticUser is not None

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict

try:
    importlib.util.find_spec("msgpack")
    HAS_MSGPACK = True
except ImportError:
    HAS_MSGPACK = False


if HAS_PYDANTIC:
    # PydanticUser is already imported from test_models
    pass
else:
    PydanticUser = None


class TypedDictUser(TypedDict):
    id: str
    name: str
    email: str
    age: int


class TestModelConverter:
    """測試模型轉換器"""

    def test_detect_dataclass_type(self):
        """測試檢測 dataclass 類型"""
        converter = ModelConverter()
        model_type = converter.detect_model_type(DataclassUser)
        assert model_type == "dataclass"

    @pytest.mark.skipif(not HAS_PYDANTIC, reason="Pydantic not available")
    def test_detect_pydantic_type(self):
        """測試檢測 Pydantic 類型"""
        converter = ModelConverter()
        model_type = converter.detect_model_type(PydanticUser)
        assert model_type == "pydantic"

    def test_detect_typeddict_type(self):
        """測試檢測 TypedDict 類型"""
        converter = ModelConverter()
        model_type = converter.detect_model_type(TypedDictUser)
        assert model_type == "typeddict"

    def test_extract_dataclass_fields(self):
        """測試提取 dataclass 欄位"""
        converter = ModelConverter()
        fields = converter.extract_fields(DataclassUser)

        assert "id" in fields
        assert "name" in fields
        assert "email" in fields
        assert "age" in fields
        assert fields["name"] is str
        assert fields["email"] is str
        # age is Optional[int] in our test model, so we just check it exists
        assert "age" in fields

    @pytest.mark.skipif(not HAS_PYDANTIC, reason="Pydantic not available")
    def test_extract_pydantic_fields(self):
        """測試提取 Pydantic 欄位"""
        converter = ModelConverter()
        fields = converter.extract_fields(PydanticUser)

        assert "name" in fields
        assert "email" in fields
        assert "age" in fields

    def test_dataclass_to_dict(self, sample_user_data):
        """測試 dataclass 轉字典"""
        converter = ModelConverter()
        user = DataclassUser(**sample_user_data)

        user_dict = converter.to_dict(user)

        assert user_dict["name"] == sample_user_data["name"]
        assert user_dict["email"] == sample_user_data["email"]
        assert user_dict["age"] == sample_user_data["age"]

    def test_dict_to_dataclass(self, sample_user_data):
        """測試字典轉 dataclass"""
        converter = ModelConverter()

        user = converter.from_dict(DataclassUser, sample_user_data)

        assert isinstance(user, DataclassUser)
        assert user.name == sample_user_data["name"]
        assert user.email == sample_user_data["email"]
        assert user.age == sample_user_data["age"]

    @pytest.mark.skipif(not HAS_PYDANTIC, reason="Pydantic not available")
    def test_pydantic_conversion(self, sample_user_data):
        """測試 Pydantic 模型轉換"""
        converter = ModelConverter()

        # 字典轉 Pydantic
        user = converter.from_dict(PydanticUser, sample_user_data)
        assert isinstance(user, PydanticUser)
        assert user.name == sample_user_data["name"]

        # Pydantic 轉字典
        user_dict = converter.to_dict(user)
        assert user_dict["name"] == sample_user_data["name"]
        assert user_dict["email"] == sample_user_data["email"]

    def test_typeddict_conversion(self, sample_user_data):
        """測試 TypedDict 轉換"""
        converter = ModelConverter()

        # 字典轉 TypedDict（實際上還是字典）
        user = converter.from_dict(TypedDictUser, sample_user_data)
        assert isinstance(user, dict)
        assert user["name"] == sample_user_data["name"]

        # TypedDict 轉字典
        user_dict = converter.to_dict(user)
        assert user_dict == sample_user_data


class TestSerializerFactory:
    """測試序列化器工廠"""

    def test_available_serializers(self):
        """測試可用的序列化器"""
        available = SerializerFactory.available_types()

        assert "json" in available
        assert "pickle" in available
        assert "msgpack" in available

    def test_create_json_serializer(self):
        """測試創建 JSON 序列化器"""
        serializer = SerializerFactory.create("json")

        test_data = {"name": "test", "value": 123}
        serialized = serializer.serialize(test_data)
        deserialized = serializer.deserialize(serialized)

        assert isinstance(serialized, bytes)
        assert deserialized == test_data

    def test_create_pickle_serializer(self):
        """測試創建 Pickle 序列化器"""
        serializer = SerializerFactory.create("pickle")

        test_data = {"name": "test", "value": 123, "list": [1, 2, 3]}
        serialized = serializer.serialize(test_data)
        deserialized = serializer.deserialize(serialized)

        assert isinstance(serialized, bytes)
        assert deserialized == test_data

    @pytest.mark.skipif(not HAS_MSGPACK, reason="msgpack not available")
    def test_create_msgpack_serializer(self):
        """測試創建 MsgPack 序列化器"""
        serializer = SerializerFactory.create("msgpack")

        test_data = {"name": "test", "value": 123}
        serialized = serializer.serialize(test_data)
        deserialized = serializer.deserialize(serialized)

        assert isinstance(serialized, bytes)
        assert deserialized == test_data

    def test_invalid_serializer_type(self):
        """測試無效的序列化器類型"""
        with pytest.raises(ValueError):
            SerializerFactory.create("invalid_type")


class TestIntegratedDataTypes:
    """測試整合的數據類型支援"""

    def test_dataclass_with_memory_storage(self, sample_user_data):
        """測試 dataclass 與內存存儲的整合"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(
            model=DataclassUser, storage=storage, resource_name="users"
        )

        created_user_id = crud.create(sample_user_data)
        retrieved_user = crud.get(created_user_id)

        assert retrieved_user is not None
        assert retrieved_user["name"] == sample_user_data["name"]

    @pytest.mark.skipif(not HAS_PYDANTIC, reason="Pydantic not available")
    def test_pydantic_with_memory_storage(self, sample_user_data):
        """測試 Pydantic 與內存存儲的整合"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(
            model=PydanticUser, storage=storage, resource_name="users"
        )

        created_user_id = crud.create(sample_user_data)
        retrieved_user = crud.get(created_user_id)

        assert retrieved_user is not None
        assert retrieved_user["name"] == sample_user_data["name"]

    def test_typeddict_with_memory_storage(self, sample_user_data):
        """測試 TypedDict 與內存存儲的整合"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(
            model=TypedDictUser, storage=storage, resource_name="users"
        )

        created_user_id = crud.create(sample_user_data)
        retrieved_user = crud.get(created_user_id)

        assert retrieved_user is not None
        assert retrieved_user["name"] == sample_user_data["name"]

    def test_different_serializers_with_storage(self, sample_user_data):
        """測試不同序列化器與存儲的組合"""
        serializer_types = ["json", "pickle"]

        for serializer_type in serializer_types:
            serializer = SerializerFactory.create(serializer_type)
            storage = MemoryStorage(serializer=serializer)
            crud = SingleModelCRUD(
                model=DataclassUser, storage=storage, resource_name="users"
            )

            created_user_id = crud.create(sample_user_data)
            retrieved_user = crud.get(created_user_id)

            assert retrieved_user is not None
            assert retrieved_user["name"] == sample_user_data["name"]
