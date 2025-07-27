"""
測試 ModelConverter 的未覆蓋代碼路徑
"""

import pytest
from autocrud.converter import ModelConverter
import importlib.util

try:
    importlib.util.find_spec("pydantic")
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False


def test_unsupported_model_type():
    """測試不支援的模型類型"""

    class UnsupportedModel:
        pass

    with pytest.raises(ValueError, match="不支援的模型類型"):
        ModelConverter.detect_model_type(UnsupportedModel)


def test_typeddict_conversion():
    """測試 TypedDict 轉換"""
    from typing import TypedDict

    class UserDict(TypedDict):
        name: str
        age: int
        email: str

    converter = ModelConverter()

    # 檢測類型
    model_type = converter.detect_model_type(UserDict)
    assert model_type == "typeddict"

    # 提取欄位
    fields = converter.extract_fields(UserDict)
    assert "name" in fields
    assert "age" in fields
    assert "email" in fields

    # 轉換為字典（TypedDict 實例本身就是字典）
    user_data = {"name": "Alice", "age": 30, "email": "alice@example.com"}
    result = converter.to_dict(user_data)
    assert result == user_data

    # 從字典創建（TypedDict 就是字典）
    new_user = converter.from_dict(UserDict, user_data)
    assert new_user == user_data


@pytest.mark.skipif(not HAS_PYDANTIC, reason="Pydantic not available")
def test_pydantic_v1_compatibility():
    """測試 Pydantic v1 兼容性（如果可用）"""

    # 嘗試創建一個有 __fields__ 的模型（模擬 v1）
    class MockPydanticV1Model:
        __fields__ = {
            "name": type("Field", (), {"type_": str}),
            "age": type("Field", (), {"type_": int}),
        }

    converter = ModelConverter()

    # 這應該被檢測為 pydantic（即使是模擬的 v1）
    model_type = converter.detect_model_type(MockPydanticV1Model)
    assert model_type == "pydantic"

    # 提取欄位應該使用 __fields__
    fields = converter.extract_fields(MockPydanticV1Model)
    assert fields.get("name") is str
    assert fields.get("age") is int


def test_dict_instance_conversion():
    """測試普通字典實例的轉換"""
    converter = ModelConverter()

    # 普通字典
    data = {"name": "Alice", "age": 30}
    result = converter.to_dict(data)
    assert result == data

    # dict 類型不被 detect_model_type 支援
    with pytest.raises(ValueError, match="不支援的模型類型"):
        converter.from_dict(dict, data)


def test_unknown_instance_conversion():
    """測試未知類型實例的轉換"""
    converter = ModelConverter()

    class UnknownType:
        def __init__(self):
            self.name = "test"

    instance = UnknownType()

    # to_dict 對於未知類型應該拋出異常
    with pytest.raises(ValueError, match="無法轉換為字典"):
        converter.to_dict(instance)

    # from_dict 對於未知類型在 detect_model_type 階段就會失敗
    with pytest.raises(ValueError, match="不支援的模型類型"):
        converter.from_dict(UnknownType, {"name": "test"})


def test_pydantic_model_with_dict_method():
    """測試有 dict() 方法的 Pydantic 模型"""

    class MockPydanticModel:
        def __init__(self, name: str, age: int):
            self.name = name
            self.age = age

        def dict(self):
            return {"name": self.name, "age": self.age}

        @classmethod
        def parse_obj(cls, data):
            return cls(**data)

    converter = ModelConverter()
    instance = MockPydanticModel("Alice", 30)

    # 應該使用 dict() 方法
    result = converter.to_dict(instance)
    assert result == {"name": "Alice", "age": 30}


def test_empty_extract_fields():
    """測試不支援類型的 extract_fields"""

    class EmptyModel:
        # 沒有 dataclass 裝飾器，沒有 pydantic 特徵，沒有 typeddict 特徵
        pass

    converter = ModelConverter()

    # 對於不支援的類型，detect_model_type 會拋出異常
    with pytest.raises(ValueError, match="不支援的模型類型"):
        converter.extract_fields(EmptyModel)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
