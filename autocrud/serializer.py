"""序列化器模組"""

import json
import pickle
from typing import Any
from abc import ABC, abstractmethod

try:
    import msgpack

    HAS_MSGPACK = True
except ImportError:
    HAS_MSGPACK = False


class Serializer(ABC):
    """序列化器抽象基類"""

    @abstractmethod
    def serialize(self, data: Any) -> bytes:
        """序列化數據"""
        pass

    @abstractmethod
    def deserialize(self, data: bytes) -> Any:
        """反序列化數據"""
        pass


class JsonSerializer(Serializer):
    """JSON 序列化器"""

    def serialize(self, data: Any) -> bytes:
        return json.dumps(data, ensure_ascii=False).encode("utf-8")

    def deserialize(self, data: bytes) -> Any:
        return json.loads(data.decode("utf-8"))


class PickleSerializer(Serializer):
    """Pickle 序列化器"""

    def serialize(self, data: Any) -> bytes:
        return pickle.dumps(data)

    def deserialize(self, data: bytes) -> Any:
        return pickle.loads(data)


class MsgPackSerializer(Serializer):
    """MsgPack 序列化器"""

    def __init__(self):
        if not HAS_MSGPACK:
            raise ImportError("需要安裝 msgpack: pip install msgpack")

    def serialize(self, data: Any) -> bytes:
        return msgpack.packb(data, use_bin_type=True)

    def deserialize(self, data: bytes) -> Any:
        return msgpack.unpackb(data, raw=False)


class SerializerFactory:
    """序列化器工廠"""

    _serializers = {
        "json": JsonSerializer,
        "pickle": PickleSerializer,
        "msgpack": MsgPackSerializer,
    }

    @classmethod
    def create(cls, serializer_type: str) -> Serializer:
        """創建序列化器實例"""
        if serializer_type not in cls._serializers:
            available = ", ".join(cls._serializers.keys())
            raise ValueError(
                f"不支援的序列化器類型: {serializer_type}. 可用類型: {available}"
            )

        serializer_class = cls._serializers[serializer_type]
        return serializer_class()

    @classmethod
    def register(cls, name: str, serializer_class: type):
        """註冊新的序列化器"""
        cls._serializers[name] = serializer_class

    @classmethod
    def available_types(cls) -> list:
        """獲取可用的序列化器類型"""
        return list(cls._serializers.keys())


# 使用範例
if __name__ == "__main__":
    # 測試 JSON 序列化器
    json_serializer = SerializerFactory.create("json")

    test_data = {"name": "Alice", "age": 30, "email": "alice@example.com"}

    # 序列化
    serialized = json_serializer.serialize(test_data)
    print(f"序列化後: {serialized}")

    # 反序列化
    deserialized = json_serializer.deserialize(serialized)
    print(f"反序列化後: {deserialized}")

    # 顯示可用的序列化器
    print(f"可用的序列化器: {SerializerFactory.available_types()}")
