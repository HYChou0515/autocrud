"""Tests for model class-based access in AutoCRUD"""

import pytest
from typing import TypedDict

from autocrud import AutoCRUD
from autocrud.storage import MemoryStorage


class User(TypedDict):
    id: str
    name: str
    email: str


class Product(TypedDict):
    id: str
    title: str
    price: float


class Order(TypedDict):
    id: str
    user_id: str
    product_id: str
    quantity: int


@pytest.fixture
def autocrud():
    """創建 AutoCRUD 實例"""
    return AutoCRUD()


@pytest.fixture
def registered_autocrud():
    """創建已註冊模型的 AutoCRUD 實例"""
    crud = AutoCRUD()
    crud.register_model(User, resource_name="users", storage=MemoryStorage())
    crud.register_model(Product, resource_name="products", storage=MemoryStorage())
    return crud


def test_get_model_by_class_single_registration(registered_autocrud):
    """測試獲取只註冊一次的模型類"""
    # 正常獲取
    model = registered_autocrud.get_model_by_class(User)
    assert model is User

    model = registered_autocrud.get_model_by_class(Product)
    assert model is Product


def test_get_model_by_class_not_registered(registered_autocrud):
    """測試獲取未註冊的模型類"""
    with pytest.raises(ValueError) as exc_info:
        registered_autocrud.get_model_by_class(Order)

    assert "Model class 'Order' not registered" in str(exc_info.value)


def test_get_model_by_class_multiple_registrations():
    """測試獲取註冊多次的模型類（應該報錯）"""
    crud = AutoCRUD()
    # 同一個模型註冊兩次，使用不同的 resource_name
    crud.register_model(User, resource_name="users", storage=MemoryStorage())
    crud.register_model(User, resource_name="customers", storage=MemoryStorage())

    with pytest.raises(ValueError) as exc_info:
        crud.get_model_by_class(User)

    error_msg = str(exc_info.value)
    assert "Model class 'User' is registered multiple times" in error_msg
    assert "users" in error_msg
    assert "customers" in error_msg
    assert "Please use get_model(resource_name) instead" in error_msg


def test_get_crud_by_class_single_registration(registered_autocrud):
    """測試根據模型類獲取 CRUD 實例"""
    crud = registered_autocrud.get_crud_by_class(User)
    assert crud is not None
    # 驗證是正確的 CRUD 實例
    assert crud.model == User

    crud = registered_autocrud.get_crud_by_class(Product)
    assert crud is not None
    assert crud.model == Product


def test_get_crud_by_class_not_registered(registered_autocrud):
    """測試獲取未註冊模型的 CRUD"""
    with pytest.raises(ValueError) as exc_info:
        registered_autocrud.get_crud_by_class(Order)

    assert "Model class 'Order' not registered" in str(exc_info.value)


def test_get_crud_by_class_multiple_registrations():
    """測試獲取註冊多次的模型類的 CRUD（應該報錯）"""
    crud = AutoCRUD()
    crud.register_model(User, resource_name="users", storage=MemoryStorage())
    crud.register_model(User, resource_name="customers", storage=MemoryStorage())

    with pytest.raises(ValueError) as exc_info:
        crud.get_crud_by_class(User)

    error_msg = str(exc_info.value)
    assert "Model class 'User' is registered multiple times" in error_msg
    assert "Please use get_crud(resource_name) instead" in error_msg


def test_get_storage_by_class_single_registration(registered_autocrud):
    """測試根據模型類獲取存儲後端"""
    storage = registered_autocrud.get_storage_by_class(User)
    assert storage is not None
    assert isinstance(storage, MemoryStorage)

    storage = registered_autocrud.get_storage_by_class(Product)
    assert storage is not None
    assert isinstance(storage, MemoryStorage)


def test_get_storage_by_class_not_registered(registered_autocrud):
    """測試獲取未註冊模型的存儲後端"""
    with pytest.raises(ValueError) as exc_info:
        registered_autocrud.get_storage_by_class(Order)

    assert "Model class 'Order' not registered" in str(exc_info.value)


def test_get_storage_by_class_multiple_registrations():
    """測試獲取註冊多次的模型類的存儲後端（應該報錯）"""
    crud = AutoCRUD()
    crud.register_model(User, resource_name="users", storage=MemoryStorage())
    crud.register_model(User, resource_name="customers", storage=MemoryStorage())

    with pytest.raises(ValueError) as exc_info:
        crud.get_storage_by_class(User)

    error_msg = str(exc_info.value)
    assert "Model class 'User' is registered multiple times" in error_msg
    assert "Please use get_storage(resource_name) instead" in error_msg


def test_list_model_classes(registered_autocrud):
    """測試列出所有註冊的模型類"""
    classes = registered_autocrud.list_model_classes()
    assert User in classes
    assert Product in classes
    assert len(classes) == 2


def test_list_model_classes_empty():
    """測試空 AutoCRUD 的模型類列表"""
    crud = AutoCRUD()
    classes = crud.list_model_classes()
    assert classes == []


def test_get_resource_names_by_class_single(registered_autocrud):
    """測試獲取單個註冊的模型類的 resource names"""
    names = registered_autocrud.get_resource_names_by_class(User)
    assert names == ["users"]

    names = registered_autocrud.get_resource_names_by_class(Product)
    assert names == ["products"]


def test_get_resource_names_by_class_multiple():
    """測試獲取多次註冊的模型類的 resource names"""
    crud = AutoCRUD()
    crud.register_model(User, resource_name="users", storage=MemoryStorage())
    crud.register_model(User, resource_name="customers", storage=MemoryStorage())

    names = crud.get_resource_names_by_class(User)
    assert set(names) == {"users", "customers"}
    assert len(names) == 2


def test_get_resource_names_by_class_not_registered(registered_autocrud):
    """測試獲取未註冊模型的 resource names"""
    with pytest.raises(ValueError) as exc_info:
        registered_autocrud.get_resource_names_by_class(Order)

    assert "Model class 'Order' not registered" in str(exc_info.value)


def test_get_resource_names_by_class_returns_copy():
    """測試 get_resource_names_by_class 返回的是副本"""
    crud = AutoCRUD()
    crud.register_model(User, resource_name="users", storage=MemoryStorage())

    names = crud.get_resource_names_by_class(User)
    original_length = len(names)

    # 修改返回的列表
    names.append("should_not_affect_original")

    # 再次獲取，應該不受影響
    names2 = crud.get_resource_names_by_class(User)
    assert len(names2) == original_length
    assert "should_not_affect_original" not in names2


def test_model_class_access_integration():
    """整合測試：確保模型類訪問與現有功能協同工作"""
    crud = AutoCRUD()
    storage = MemoryStorage()

    # 註冊模型
    crud.register_model(
        User, resource_name="users", storage=storage
    )  # 通過不同方式獲取應該得到相同結果
    model_by_name = crud.get_model("users")
    model_by_class = crud.get_model_by_class(User)
    assert model_by_name is model_by_class is User

    crud_by_name = crud.get_crud("users")
    crud_by_class = crud.get_crud_by_class(User)
    assert crud_by_name is crud_by_class

    storage_by_name = crud.get_storage("users")
    storage_by_class = crud.get_storage_by_class(User)
    assert storage_by_name is storage_by_class is storage


def test_model_class_mapping_consistency():
    """測試模型類映射的一致性"""
    crud = AutoCRUD()

    # 註冊多個模型
    crud.register_model(User, resource_name="users", storage=MemoryStorage())
    crud.register_model(Product, resource_name="products", storage=MemoryStorage())
    crud.register_model(
        Order, resource_name="orders", storage=MemoryStorage()
    )  # 檢查映射一致性
    all_classes = crud.list_model_classes()
    assert len(all_classes) == 3
    assert User in all_classes
    assert Product in all_classes
    assert Order in all_classes

    # 每個類都應該有對應的 resource name
    for model_class in all_classes:
        resource_names = crud.get_resource_names_by_class(model_class)
        assert len(resource_names) == 1

        # 通過 resource name 應該能找回相同的模型
        resource_name = resource_names[0]
        found_model = crud.get_model(resource_name)
        assert found_model is model_class
