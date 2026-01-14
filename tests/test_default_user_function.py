"""Test default_user as a function"""

import datetime as dt
from msgspec import Struct
from autocrud import AutoCRUD
import uuid


class SampleModel(Struct):
    name: str
    value: int


def test_default_user_as_string():
    """測試 default_user 為字串的情況"""
    crud = AutoCRUD(default_user="system")
    crud.add_model(SampleModel)

    mgr = crud.get_resource_manager(SampleModel)

    # 測試不提供 user 時會使用預設值
    with mgr.meta_provide(now=dt.datetime.now()):
        result = mgr.create(SampleModel(name="test", value=1))

    assert result.created_by == "system"
    assert result.updated_by == "system"


def test_default_user_as_function():
    """測試 default_user 為 function 的情況"""
    users_created = []

    def get_user():
        user = f"user_{len(users_created) + 1}"
        users_created.append(user)
        return user

    crud = AutoCRUD(default_user=get_user)
    crud.add_model(SampleModel)

    mgr = crud.get_resource_manager(SampleModel)

    # 測試每次都會呼叫 function
    with mgr.meta_provide(now=dt.datetime.now()):
        result1 = mgr.create(SampleModel(name="test1", value=1))

    with mgr.meta_provide(now=dt.datetime.now()):
        result2 = mgr.create(SampleModel(name="test2", value=2))

    # 驗證 function 被呼叫了，並且產生了不同的 user
    assert len(users_created) >= 2  # function 被呼叫至少 2 次
    # 兩個資源應該使用不同的 user (因為每次呼叫 function 都產生新值)
    assert result1.created_by.startswith("user_")
    assert result2.created_by.startswith("user_")


def test_default_user_override():
    """測試可以覆蓋 default_user"""

    def get_user():
        return "default_user"

    crud = AutoCRUD(default_user=get_user)
    crud.add_model(SampleModel)

    mgr = crud.get_resource_manager(SampleModel)

    # 測試明確提供 user 時會覆蓋預設值
    with mgr.meta_provide(user="custom_user", now=dt.datetime.now()):
        result = mgr.create(SampleModel(name="test", value=1))

    assert result.created_by == "custom_user"


def test_add_model_default_user_function():
    """測試在 add_model 時指定 default_user function"""

    def get_user():
        return "model_specific_user"

    crud = AutoCRUD()
    crud.add_model(SampleModel, default_user=get_user)

    mgr = crud.get_resource_manager(SampleModel)

    with mgr.meta_provide(now=dt.datetime.now()):
        result = mgr.create(SampleModel(name="test", value=1))

    assert result.created_by == "model_specific_user"


def test_default_user_uuid_generator():
    """測試使用 UUID 作為 default_user 的實際案例"""

    def generate_session_id():
        return f"session_{uuid.uuid4().hex[:8]}"

    crud = AutoCRUD(default_user=generate_session_id)
    crud.add_model(SampleModel)

    mgr = crud.get_resource_manager(SampleModel)

    with mgr.meta_provide(now=dt.datetime.now()):
        result = mgr.create(SampleModel(name="test", value=1))

    # 驗證格式
    assert result.created_by.startswith("session_")
    assert len(result.created_by) == len("session_") + 8


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
