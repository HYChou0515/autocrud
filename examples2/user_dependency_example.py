"""
CreateRouteTemplate 使用 DependencyProvider 的範例
"""

from fastapi import HTTPException, Header
from typing import Annotated
import msgspec

from autocrud.crud.core import AutoCRUD, CreateRouteTemplate, DependencyProvider
from autocrud.resource_manager.basic import IStorage
from autocrud.resource_manager.core import SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore


# 測試用的模型
class User(msgspec.Struct):
    name: str
    email: str
    age: int


def create_user_storage() -> IStorage[User]:
    """創建用戶存儲"""
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore[User](resource_type=User)
    return SimpleStorage(meta_store, resource_store)


# 示例 1: 從 Header 獲取用戶信息
def get_current_user_from_header(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """
    從 Authorization header 獲取當前用戶
    這是一個簡單的範例，實際應用中可能會：
    1. 解析 JWT token
    2. 驗證用戶身份
    3. 從數據庫查詢用戶信息
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    # 簡單示例：假設 header 格式為 "Bearer username"
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    username = authorization[7:]  # 移除 "Bearer " 前綴
    if not username:
        raise HTTPException(status_code=401, detail="Invalid username")

    return username


def main():
    """主函數 - 展示不同的使用方式"""

    # 範例 1: 不使用任何 dependency（預設行為）
    print("=== 範例 1: 預設行為（使用預設 dependency）===")
    autocrud_default = AutoCRUD(model_naming="kebab")
    autocrud_default.add_route_template(
        CreateRouteTemplate()
    )  # 使用預設 DependencyProvider
    autocrud_default.add_model(User, storage_factory=create_user_storage)

    # 範例 2: 使用自定義的 get_user dependency
    print("=== 範例 2: 使用 Authorization Header ===")
    deps_with_header = DependencyProvider(get_user=get_current_user_from_header)
    autocrud_with_header = AutoCRUD(model_naming="kebab")
    autocrud_with_header.add_route_template(
        CreateRouteTemplate(dependency_provider=deps_with_header)
    )
    autocrud_with_header.add_model(User, storage_factory=create_user_storage)

    # 範例 3: 使用自定義的 get_user 和 get_now dependency
    print("=== 範例 3: 使用自定義 dependency ===")

    def custom_get_user() -> str:
        """自定義獲取用戶的邏輯"""
        return "custom_user_123"

    def custom_get_now():
        """自定義獲取時間的邏輯"""
        import datetime as dt

        # 例如：使用 UTC 時間
        return dt.datetime.utcnow()

    deps_custom = DependencyProvider(get_user=custom_get_user, get_now=custom_get_now)
    autocrud_custom = AutoCRUD(model_naming="kebab")
    autocrud_custom.add_route_template(
        CreateRouteTemplate(dependency_provider=deps_custom)
    )
    autocrud_custom.add_model(User, storage_factory=create_user_storage)

    print("所有範例設置完成！")
    print("""
使用方式：

1. 預設行為：
   POST /user
   Body: {"name": "John", "email": "john@example.com", "age": 30}
   → 使用 "system" 作為創建者，現在時間作為創建時間

2. 使用 Header：
   POST /user
   Headers: Authorization: Bearer john_doe
   Body: {"name": "John", "email": "john@example.com", "age": 30}
   → 使用 "john_doe" 作為創建者，現在時間作為創建時間

3. 使用自定義邏輯：
   POST /user  
   Body: {"name": "John", "email": "john@example.com", "age": 30}
   → 使用 "custom_user_123" 作為創建者，UTC 時間作為創建時間
   """)


if __name__ == "__main__":
    main()


# 示例 2: 從 Cookie 或其他來源獲取用戶信息
def get_current_user_from_cookie(request) -> str:
    """從 cookie 獲取用戶信息的範例"""
    # 這裡可以實現從 cookie 讀取用戶信息的邏輯
    return "user_from_cookie"


def main():
    """主函數 - 展示不同的使用方式"""

    # 範例 1: 不使用 user dependency（預設行為）
    print("=== 範例 1: 預設行為（使用 'system' 用戶）===")
    autocrud_default = AutoCRUD(model_naming="kebab")
    autocrud_default.add_route_template(CreateRouteTemplate())  # 不傳入 dependency
    autocrud_default.add_model(User, storage_factory=create_user_storage)

    # 範例 2: 使用 Header dependency
    print("=== 範例 2: 使用 Authorization Header ===")
    autocrud_with_header = AutoCRUD(model_naming="kebab")
    autocrud_with_header.add_route_template(
        CreateRouteTemplate(get_user=get_current_user_from_header)
    )
    autocrud_with_header.add_model(User, storage_factory=create_user_storage)

    # 範例 3: 使用自定義 dependency
    print("=== 範例 3: 使用自定義 dependency ===")

    def custom_get_user() -> str:
        """自定義獲取用戶的邏輯"""
        # 這裡可以實現任何獲取當前用戶的邏輯
        # 例如：從 JWT token、session、database 等
        return "custom_user_123"

    autocrud_custom = AutoCRUD(model_naming="kebab")
    autocrud_custom.add_route_template(CreateRouteTemplate(get_user=custom_get_user))
    autocrud_custom.add_model(User, storage_factory=create_user_storage)

    print("所有範例設置完成！")
    print("""
使用方式：

1. 預設行為：
   POST /user
   Body: {"name": "John", "email": "john@example.com", "age": 30}
   → 使用 "system" 作為創建者

2. 使用 Header：
   POST /user
   Headers: Authorization: Bearer john_doe
   Body: {"name": "John", "email": "john@example.com", "age": 30}
   → 使用 "john_doe" 作為創建者

3. 使用自定義邏輯：
   POST /user  
   Body: {"name": "John", "email": "john@example.com", "age": 30}
   → 使用 "custom_user_123" 作為創建者
   """)


if __name__ == "__main__":
    main()
