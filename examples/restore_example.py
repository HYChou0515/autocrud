"""
RestoreRouteTemplate 使用示例

這個示例展示如何使用 RestoreRouteTemplate 來恢復已刪除的資源。
"""

from fastapi import FastAPI
import msgspec

from autocrud.v03.crud.core import (
    AutoCRUD,
    CreateRouteTemplate,
    ReadRouteTemplate,
    DeleteRouteTemplate,
    RestoreRouteTemplate,
)
from autocrud.v03.resource_manager.basic import IStorage
from autocrud.v03.resource_manager.core import SimpleStorage
from autocrud.v03.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.v03.resource_manager.resource_store.simple import MemoryResourceStore


# 定義用戶模型
class User(msgspec.Struct):
    name: str
    email: str
    age: int


def create_user_storage() -> IStorage[User]:
    """創建用戶存儲"""
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore[User](resource_type=User)
    return SimpleStorage(meta_store, resource_store)


# 創建 FastAPI 應用
app = FastAPI(title="Restore Example API", version="1.0.0")

# 創建 AutoCRUD 實例
crud = AutoCRUD(model_naming="kebab")

# 添加路由模板
crud.add_route_template(CreateRouteTemplate())  # 創建資源
crud.add_route_template(ReadRouteTemplate())  # 讀取資源
crud.add_route_template(DeleteRouteTemplate())  # 刪除資源
crud.add_route_template(RestoreRouteTemplate())  # 恢復資源

# 添加 User 模型
crud.add_model(User, storage_factory=create_user_storage)

# 將路由添加到 FastAPI 應用
app.include_router(crud.create_router())


if __name__ == "__main__":
    import uvicorn

    print("啟動服務器...")
    print("API 文檔: http://localhost:8000/docs")
    print("\n使用示例:")
    print("1. 創建用戶: POST /user")
    print("2. 讀取用戶: GET /user/{id}")
    print("3. 刪除用戶: DELETE /user/{id}")
    print("4. 恢復用戶: POST /user/{id}/restore")

    uvicorn.run(app, host="0.0.0.0", port=8000)
