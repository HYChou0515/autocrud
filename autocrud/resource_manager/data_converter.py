import json
from typing import Any, TypeVar

import msgspec

T = TypeVar("T")


class DataConverter:
    """數據轉換器，處理不同數據類型的序列化和反序列化"""

    def __init__(self, resource_type: type[T]):
        self.resource_type = resource_type

    @staticmethod
    def data_to_builtins(data: msgspec.Raw | T) -> Any:
        """將數據轉換為 Python 內建類型，特殊處理 msgspec.Raw"""
        if isinstance(data, msgspec.Raw):
            # 如果是 Raw 數據，先解碼為 JSON，再解析為 Python 對象
            return json.loads(bytes(data))
        # 對於其他類型，使用 msgspec.to_builtins
        return msgspec.to_builtins(data)

    def builtins_to_data(self, obj: Any) -> msgspec.Raw | T:
        return msgspec.convert(obj, self.resource_type)
