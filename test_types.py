"""測試不同數據類型和序列化格式"""

from dataclasses import dataclass
from autocrud import AutoCRUD, MemoryStorage, SerializerFactory

# 嘗試導入可選依賴
try:
    from pydantic import BaseModel

    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False
    BaseModel = None

# TypedDict 測試
try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict


# 測試不同的數據模型
@dataclass
class DataclassUser:
    name: str
    email: str
    age: int


if HAS_PYDANTIC:

    class PydanticUser(BaseModel):
        name: str
        email: str
        age: int
else:
    PydanticUser = None


class TypedDictUser(TypedDict):
    name: str
    email: str
    age: int


def test_different_models():
    """測試不同數據模型"""
    print("=== 測試不同數據模型 ===")

    test_data = {"name": "Alice", "email": "alice@example.com", "age": 30}

    # 1. 測試 Dataclass
    print("\n1. 測試 Dataclass")
    dataclass_crud = AutoCRUD(
        model=DataclassUser, storage=MemoryStorage(), resource_name="dataclass_users"
    )

    dc_user = dataclass_crud.create(test_data)
    print(f"Dataclass 用戶: {dc_user}")

    # 2. 測試 Pydantic
    if HAS_PYDANTIC:
        print("\n2. 測試 Pydantic")
        pydantic_crud = AutoCRUD(
            model=PydanticUser, storage=MemoryStorage(), resource_name="pydantic_users"
        )

        py_user = pydantic_crud.create(test_data)
        print(f"Pydantic 用戶: {py_user}")
    else:
        print("\n2. Pydantic 不可用 (未安裝)")

    # 3. 測試 TypedDict
    print("\n3. 測試 TypedDict")
    try:
        typeddict_crud = AutoCRUD(
            model=TypedDictUser,
            storage=MemoryStorage(),
            resource_name="typeddict_users",
        )

        td_user = typeddict_crud.create(test_data)
        print(f"TypedDict 用戶: {td_user}")
    except Exception as e:
        print(f"TypedDict 測試失敗: {e}")


def test_different_serializers():
    """測試不同序列化格式"""
    print("\n=== 測試不同序列化格式 ===")

    test_data = {"name": "Bob", "email": "bob@example.com", "age": 25}

    # 測試 JSON 序列化
    print("\n1. 測試 JSON 序列化")
    json_serializer = SerializerFactory.create("json")
    json_storage = MemoryStorage(serializer=json_serializer)
    json_crud = AutoCRUD(
        model=DataclassUser, storage=json_storage, resource_name="json_users"
    )

    json_user = json_crud.create(test_data)
    print(f"JSON 用戶: {json_user}")

    # 測試 Pickle 序列化
    print("\n2. 測試 Pickle 序列化")
    pickle_serializer = SerializerFactory.create("pickle")
    pickle_storage = MemoryStorage(serializer=pickle_serializer)
    pickle_crud = AutoCRUD(
        model=DataclassUser, storage=pickle_storage, resource_name="pickle_users"
    )

    pickle_user = pickle_crud.create(test_data)
    print(f"Pickle 用戶: {pickle_user}")

    # 測試 MsgPack 序列化
    print("\n3. 測試 MsgPack 序列化")
    try:
        msgpack_serializer = SerializerFactory.create("msgpack")
        msgpack_storage = MemoryStorage(serializer=msgpack_serializer)
        msgpack_crud = AutoCRUD(
            model=DataclassUser, storage=msgpack_storage, resource_name="msgpack_users"
        )

        msgpack_user = msgpack_crud.create(test_data)
        print(f"MsgPack 用戶: {msgpack_user}")
    except ImportError as e:
        print(f"MsgPack 不可用: {e}")

    # 顯示可用序列化器
    print(f"\n可用的序列化器: {SerializerFactory.available_types()}")


if __name__ == "__main__":
    test_different_models()
    test_different_serializers()
