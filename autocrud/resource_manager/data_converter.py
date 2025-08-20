import dataclasses
from enum import StrEnum
from typing import Any, TypeVar
from msgspec import Struct
import json
from typing import is_typeddict
import msgspec


try:
    import pydantic
except ImportError:
    pydantic = None

T = TypeVar("T")


class ResourceBaseType(StrEnum):
    MSGSPEC = "msgspec"
    DATACLASS = "dataclass"
    TYPEDDICT = "typeddict"
    PYDANTIC = "pydantic"
    UNKNOWN = "unknown"


class DataConverter:
    """數據轉換器，處理不同數據類型的序列化和反序列化"""

    def __init__(self, resource_type: type[T]):
        self.resource_type = resource_type
        if pydantic is not None and issubclass(resource_type, pydantic.BaseModel):
            self.base_type = ResourceBaseType.PYDANTIC
        elif dataclasses.is_dataclass(resource_type):
            self.base_type = ResourceBaseType.DATACLASS
        elif issubclass(resource_type, Struct):
            self.base_type = ResourceBaseType.MSGSPEC
        elif is_typeddict(resource_type):
            self.base_type = ResourceBaseType.TYPEDDICT
        else:
            self.base_type = ResourceBaseType.UNKNOWN

    def decode_json_to_data(self, json_bytes: bytes) -> msgspec.Raw | T:
        """將 JSON bytes 轉換為指定類型的數據"""
        if self.base_type is ResourceBaseType.PYDANTIC:
            # self.resource_type: pydantic.BaseModel
            # 對於 Pydantic 模型，先解析為字典再創建實例，然後存儲為 Raw
            json_data = json.loads(json_bytes)
            pydantic_instance = self.resource_type.model_validate(json_data)
            # 將 Pydantic 實例序列化為 Raw 格式存儲
            return msgspec.Raw(pydantic_instance.model_dump_json().encode())
        else:
            # 對於其他類型，使用 msgspec 直接解析
            return msgspec.json.decode(json_bytes, type=self.resource_type)

    @staticmethod
    def data_to_builtins(data: msgspec.Raw | T) -> Any:
        """將數據轉換為 Python 內建類型，特殊處理 msgspec.Raw"""
        if isinstance(data, msgspec.Raw):
            # 如果是 Raw 數據，先解碼為 JSON，再解析為 Python 對象
            return json.loads(bytes(data))
        else:
            # 對於其他類型，使用 msgspec.to_builtins
            return msgspec.to_builtins(data)

    def builtins_to_data(self, obj: Any) -> msgspec.Raw | T:
        if self.base_type is ResourceBaseType.PYDANTIC:
            # self.resource_type: pydantic.BaseModel
            pydantic_instance = self.resource_type.model_validate(obj)
            return msgspec.Raw(pydantic_instance.model_dump_json().encode())
        return msgspec.convert(obj, self.resource_type)

    def set_data_value(self, obj: T | msgspec.Raw, key: str, value: Any):
        if self.base_type is ResourceBaseType.PYDANTIC:
            # self.resource_type: pydantic.BaseModel
            d = self.data_to_builtins(obj)
            d[key] = value
            if isinstance(obj, msgspec.Raw):
                return msgspec.Raw(json.dumps(d).encode("utf-8"))
            else:
                return d
        if self.base_type is ResourceBaseType.MSGSPEC:
            setattr(obj, key, value)
            return obj
        if self.base_type is ResourceBaseType.DATACLASS:
            setattr(obj, key, value)
            return obj
        if self.base_type is ResourceBaseType.TYPEDDICT:
            obj[key] = value
            return obj
        # Unknown
        setattr(obj, key, value)
        return obj


def decode_json_to_data(json_bytes: bytes, resource_type: type):
    return DataConverter(resource_type).decode_json_to_data(json_bytes)


def data_to_builtins(data: msgspec.Raw | T) -> Any:
    return DataConverter.data_to_builtins(data)


def builtins_to_data(resource_type: type[T], obj: Any) -> msgspec.Raw | T:
    return DataConverter(resource_type).builtins_to_data(obj)
