"""數據類型轉換器模組"""

from typing import Any, Dict, Type, get_type_hints
from dataclasses import dataclass, is_dataclass, fields

# 嘗試導入 TypedDict，Python 3.8+ 可從 typing 導入
try:
    from typing import _TypedDictMeta  # 用於類型檢查
except ImportError:
    _TypedDictMeta = None


class ModelConverter:
    """統一的數據模型轉換器"""

    @staticmethod
    def detect_model_type(model_class: Type) -> str:
        """檢測模型類型"""
        if is_dataclass(model_class):
            return "dataclass"

        # 檢查是否為 Pydantic 模型
        if (
            hasattr(model_class, "__pydantic_core_schema__")
            or hasattr(model_class, "model_fields")
            or hasattr(model_class, "__fields__")
        ):
            return "pydantic"

        # 檢查是否為 TypedDict
        if hasattr(model_class, "__annotations__") and hasattr(
            model_class, "__total__"
        ):
            return "typeddict"

        raise ValueError(f"不支援的模型類型: {model_class}")

    @staticmethod
    def extract_fields(model_class: Type) -> Dict[str, Type]:
        """提取模型的欄位和類型"""
        model_type = ModelConverter.detect_model_type(model_class)

        if model_type == "dataclass":
            return {field.name: field.type for field in fields(model_class)}

        elif model_type == "pydantic":
            # Pydantic v2
            if hasattr(model_class, "model_fields"):
                return {
                    name: field.annotation
                    for name, field in model_class.model_fields.items()
                }
            # Pydantic v1
            elif hasattr(model_class, "__fields__"):
                return {
                    name: field.type_ for name, field in model_class.__fields__.items()
                }

        elif model_type == "typeddict":
            return get_type_hints(model_class)

        return {}

    @staticmethod
    def to_dict(instance: Any) -> Dict[str, Any]:
        """將模型實例轉換為字典"""
        if is_dataclass(instance):
            from dataclasses import asdict

            return asdict(instance)

        # Pydantic 模型
        if hasattr(instance, "model_dump"):
            return instance.model_dump()
        elif hasattr(instance, "dict"):
            return instance.dict()

        # TypedDict 或普通字典
        if isinstance(instance, dict):
            return instance

        raise ValueError(f"無法轉換為字典: {type(instance)}")

    @staticmethod
    def from_dict(model_class: Type, data: Dict[str, Any]) -> Any:
        """從字典創建模型實例"""
        model_type = ModelConverter.detect_model_type(model_class)

        if model_type == "dataclass":
            return model_class(**data)

        elif model_type == "pydantic":
            return model_class(**data)

        elif model_type == "typeddict":
            # TypedDict 只是類型提示，實際上還是字典
            return data

        raise ValueError(f"無法從字典創建實例: {model_class}")


# 使用範例
if __name__ == "__main__":
    from dataclasses import dataclass
    from typing import Dict

    @dataclass
    class User:
        name: str
        age: int
        email: str

    # 測試轉換器
    converter = ModelConverter()

    # 檢測類型
    print(f"模型類型: {converter.detect_model_type(User)}")

    # 提取欄位
    fields_info = converter.extract_fields(User)
    print(f"欄位信息: {fields_info}")

    # 創建實例並轉換
    user = User(name="Alice", age=30, email="alice@example.com")
    user_dict = converter.to_dict(user)
    print(f"轉為字典: {user_dict}")

    # 從字典創建實例
    new_user = converter.from_dict(User, user_dict)
    print(f"從字典創建: {new_user}")
