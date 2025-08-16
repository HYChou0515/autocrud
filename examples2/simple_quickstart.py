#!/usr/bin/env python3
"""
AutoCRUD 快速開始示例

這個示例展示了如何用最少的代碼創建一個支持多種數據類型的 CRUD API。
AutoCRUD 支持：
- TypedDict
- Pydantic BaseModel
- dataclass
- msgspec.Struct
"""

from dataclasses import dataclass
from typing import Optional, TypedDict
from pydantic import BaseModel
import msgspec
from fastapi import FastAPI, APIRouter
import uvicorn

from autocrud.crud.core import (
    AutoCRUD,
    CreateRouteTemplate,
    ReadRouteTemplate,
    UpdateRouteTemplate,
    DeleteRouteTemplate,
    ListRouteTemplate,
)


# 定義不同類型的用戶模型


# 1. TypedDict 方式 - 輕量級字典類型
class TypedDictUser(TypedDict):
    name: str
    email: str
    age: Optional[int]


# 2. Pydantic 方式 - 強大的數據驗證
class PydanticUser(BaseModel):
    name: str
    email: str
    age: Optional[int] = None


# 3. dataclass 方式 - Python 原生數據類
@dataclass
class DataclassUser:
    name: str
    email: str
    age: Optional[int] = None


# 4. msgspec 方式 - 高性能序列化
class MsgspecUser(msgspec.Struct):
    name: str
    email: str
    age: Optional[int] = None


def create_app() -> FastAPI:
    """創建 FastAPI 應用"""
    # 1. 創建 AutoCRUD 實例
    crud = AutoCRUD(model_naming="kebab")  # 使用 kebab-case 命名

    # 2. 添加所有 CRUD 路由模板
    crud.add_route_template(CreateRouteTemplate())
    crud.add_route_template(ReadRouteTemplate())
    crud.add_route_template(UpdateRouteTemplate())
    crud.add_route_template(DeleteRouteTemplate())
    crud.add_route_template(ListRouteTemplate())

    # 3. 註冊數據模型 - 就這麼簡單！
    crud.add_model(TypedDictUser)  # 生成 /typed-dict-user 路由
    crud.add_model(PydanticUser)  # 生成 /pydantic-user 路由
    crud.add_model(DataclassUser)  # 生成 /dataclass-user 路由
    crud.add_model(MsgspecUser)  # 生成 /msgspec-user 路由

    # 4. 創建 FastAPI 應用並應用路由
    app = FastAPI(title="AutoCRUD Multi-Type Demo")
    router = APIRouter()
    crud.apply(router)
    app.include_router(router)

    return app


def main():
    """運行開發服務器"""
    app = create_app()

    print("🚀 AutoCRUD 服務器啟動！")
    print("\n📝 可用的 API 端點:")
    print("  TypedDict 用戶: http://localhost:8000/typed-dict-user")
    print("  Pydantic 用戶:  http://localhost:8000/pydantic-user")
    print("  Dataclass 用戶: http://localhost:8000/dataclass-user")
    print("  Msgspec 用戶:   http://localhost:8000/msgspec-user")
    print("\n🔗 API 文檔: http://localhost:8000/docs")
    print("🔗 替代文檔: http://localhost:8000/redoc")

    # 啟動開發服務器
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
