"""測試 AutoCRUD 基本功能"""

from dataclasses import dataclass
from autocrud import AutoCRUD, MemoryStorage


@dataclass
class User:
    name: str
    email: str
    age: int


def test_basic_crud():
    """測試基本 CRUD 功能"""
    print("=== 測試基本 CRUD 功能 ===")

    # 創建 AutoCRUD 實例
    storage = MemoryStorage()
    crud = AutoCRUD(model=User, storage=storage, resource_name="users")

    # 1. 測試創建
    print("\n1. 測試創建用戶")
    user_data = {"name": "Alice", "email": "alice@example.com", "age": 30}
    created_user = crud.create(user_data)
    print(f"創建用戶: {created_user}")
    user_id = created_user["id"]

    # 2. 測試獲取
    print("\n2. 測試獲取用戶")
    retrieved_user = crud.get(user_id)
    print(f"獲取用戶: {retrieved_user}")

    # 3. 測試存在檢查
    print("\n3. 測試存在檢查")
    exists = crud.exists(user_id)
    print(f"用戶存在: {exists}")

    # 4. 測試更新
    print("\n4. 測試更新用戶")
    updated_data = {
        "name": "Alice Smith",
        "email": "alice.smith@example.com",
        "age": 31,
    }
    updated_user = crud.update(user_id, updated_data)
    print(f"更新用戶: {updated_user}")

    # 5. 創建更多用戶
    print("\n5. 創建更多用戶")
    user2_data = {"name": "Bob", "email": "bob@example.com", "age": 25}
    user3_data = {"name": "Charlie", "email": "charlie@example.com", "age": 35}

    created_user2 = crud.create(user2_data)
    created_user3 = crud.create(user3_data)
    print(f"創建用戶2: {created_user2}")
    print(f"創建用戶3: {created_user3}")

    # 6. 測試列出所有
    print("\n6. 測試列出所有用戶")
    all_users = crud.list_all()
    print(f"所有用戶 ({len(all_users)} 個):")
    for uid, user in all_users.items():
        print(f"  {uid}: {user}")

    # 7. 測試刪除
    print("\n7. 測試刪除用戶")
    deleted = crud.delete(user_id)
    print(f"刪除用戶 {user_id}: {deleted}")

    # 8. 確認刪除
    print("\n8. 確認刪除")
    exists_after_delete = crud.exists(user_id)
    print(f"刪除後用戶存在: {exists_after_delete}")

    final_users = crud.list_all()
    print(f"剩餘用戶 ({len(final_users)} 個):")
    for uid, user in final_users.items():
        print(f"  {uid}: {user}")


if __name__ == "__main__":
    test_basic_crud()
