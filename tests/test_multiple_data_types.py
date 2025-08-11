"""測試 AutoCRUD 對不同數據類型的支持"""

import pytest
from dataclasses import dataclass, asdict
from typing import Optional, TypedDict
from pydantic import BaseModel
import msgspec
from fastapi import FastAPI, APIRouter
from fastapi.testclient import TestClient

from autocrud.crud.core import (
    AutoCRUD,
    CreateRouteTemplate,
    ReadRouteTemplate,
    UpdateRouteTemplate,
    DeleteRouteTemplate,
    ListRouteTemplate,
)


# 1. TypedDict 方式
class TypedDictUser(TypedDict):
    name: str
    email: str
    age: Optional[int]


# 2. Pydantic 方式
class PydanticUser(BaseModel):
    name: str
    email: str
    age: Optional[int] = None


# 3. Dataclass 方式
@dataclass
class DataclassUser:
    name: str
    email: str
    age: Optional[int] = None


# 4. Msgspec 方式
class MsgspecUser(msgspec.Struct):
    name: str
    email: str
    age: Optional[int] = None


@pytest.fixture
def autocrud():
    """創建 AutoCRUD 實例並註冊所有數據類型"""
    crud = AutoCRUD(model_naming="kebab")

    # 添加基本路由模板
    crud.add_route_template(CreateRouteTemplate())
    crud.add_route_template(ReadRouteTemplate())
    crud.add_route_template(UpdateRouteTemplate())
    crud.add_route_template(DeleteRouteTemplate())
    crud.add_route_template(ListRouteTemplate())

    # 註冊所有數據類型 - 用戶期望的簡潔API
    crud.add_model(TypedDictUser)
    crud.add_model(PydanticUser)
    crud.add_model(DataclassUser)
    crud.add_model(MsgspecUser)

    return crud


@pytest.fixture
def client(autocrud):
    """創建測試客戶端"""
    app = FastAPI()
    router = APIRouter()
    autocrud.apply(router)
    app.include_router(router)
    return TestClient(app)


@pytest.mark.parametrize(
    "user_data,endpoint",
    [
        (
            TypedDictUser(name="TypedDict User", email="typed@example.com", age=25),
            "typed-dict-user",
        ),
        (
            PydanticUser(name="Pydantic User", email="pydantic@example.com", age=30),
            "pydantic-user",
        ),
        (
            DataclassUser(name="Dataclass User", email="dataclass@example.com", age=35),
            "dataclass-user",
        ),
        (
            MsgspecUser(name="Msgspec User", email="msgspec@example.com", age=40),
            "msgspec-user",
        ),
    ],
)
class TestCreateOperations:
    """測試不同數據類型的創建操作"""

    def test_create_user(self, client: TestClient, user_data, endpoint):
        """測試創建用戶 - 統一測試所有數據類型"""
        # 將不同類型的對象轉換為字典形式供 JSON 序列化
        if isinstance(user_data, BaseModel):  # Pydantic
            json_data = user_data.model_dump()
        elif hasattr(user_data, "__dataclass_fields__"):  # Dataclass
            json_data = asdict(user_data)
        elif isinstance(user_data, msgspec.Struct):  # Msgspec
            json_data = msgspec.to_builtins(user_data)
        else:  # TypedDict (already a dict)
            json_data = user_data

        response = client.post(f"/{endpoint}", json=json_data)

        # 所有數據類型都應該能成功創建
        assert response.status_code == 200
