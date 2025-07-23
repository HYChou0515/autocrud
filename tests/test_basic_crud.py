"""測試基本 CRUD 功能"""

from dataclasses import dataclass
from autocrud import AutoCRUD, MemoryStorage


@dataclass
class User:
    name: str
    email: str
    age: int


class TestBasicCrud:
    """測試基本 CRUD 功能"""

    def test_create_user(self, sample_user_data):
        """測試創建用戶"""
        storage = MemoryStorage()
        crud = AutoCRUD(model=User, storage=storage, resource_name="users")

        created_user = crud.create(sample_user_data)

        assert created_user["name"] == sample_user_data["name"]
        assert created_user["email"] == sample_user_data["email"]
        assert created_user["age"] == sample_user_data["age"]
        assert "id" in created_user
        assert isinstance(created_user["id"], str)

    def test_get_user(self, sample_user_data):
        """測試獲取用戶"""
        storage = MemoryStorage()
        crud = AutoCRUD(model=User, storage=storage, resource_name="users")

        # 先創建用戶
        created_user = crud.create(sample_user_data)
        user_id = created_user["id"]

        # 獲取用戶
        retrieved_user = crud.get(user_id)

        assert retrieved_user is not None
        assert retrieved_user["id"] == user_id
        assert retrieved_user["name"] == sample_user_data["name"]

    def test_get_nonexistent_user(self):
        """測試獲取不存在的用戶"""
        storage = MemoryStorage()
        crud = AutoCRUD(model=User, storage=storage, resource_name="users")

        result = crud.get("nonexistent-id")
        assert result is None

    def test_update_user(self, sample_user_data):
        """測試更新用戶"""
        storage = MemoryStorage()
        crud = AutoCRUD(model=User, storage=storage, resource_name="users")

        # 創建用戶
        created_user = crud.create(sample_user_data)
        user_id = created_user["id"]

        # 更新用戶
        updated_data = {
            "name": "Alice Smith",
            "email": "alice.smith@example.com",
            "age": 31,
        }
        updated_user = crud.update(user_id, updated_data)

        assert updated_user is not None
        assert updated_user["id"] == user_id
        assert updated_user["name"] == "Alice Smith"
        assert updated_user["email"] == "alice.smith@example.com"
        assert updated_user["age"] == 31

    def test_update_nonexistent_user(self, sample_user_data):
        """測試更新不存在的用戶"""
        storage = MemoryStorage()
        crud = AutoCRUD(model=User, storage=storage, resource_name="users")

        result = crud.update("nonexistent-id", sample_user_data)
        assert result is None

    def test_delete_user(self, sample_user_data):
        """測試刪除用戶"""
        storage = MemoryStorage()
        crud = AutoCRUD(model=User, storage=storage, resource_name="users")

        # 創建用戶
        created_user = crud.create(sample_user_data)
        user_id = created_user["id"]

        # 確認用戶存在
        assert crud.exists(user_id) is True

        # 刪除用戶
        deleted = crud.delete(user_id)
        assert deleted is True

        # 確認用戶不存在
        assert crud.exists(user_id) is False
        assert crud.get(user_id) is None

    def test_delete_nonexistent_user(self):
        """測試刪除不存在的用戶"""
        storage = MemoryStorage()
        crud = AutoCRUD(model=User, storage=storage, resource_name="users")

        result = crud.delete("nonexistent-id")
        assert result is False

    def test_list_all_users(self, sample_user_data):
        """測試列出所有用戶"""
        storage = MemoryStorage()
        crud = AutoCRUD(model=User, storage=storage, resource_name="users")

        # 創建多個用戶
        user1 = crud.create(sample_user_data)
        user2_data = {"name": "Bob", "email": "bob@example.com", "age": 25}
        user2 = crud.create(user2_data)

        # 列出所有用戶
        all_users = crud.list_all()

        assert len(all_users) == 2
        assert user1["id"] in all_users
        assert user2["id"] in all_users
        assert all_users[user1["id"]]["name"] == "Alice"
        assert all_users[user2["id"]]["name"] == "Bob"

    def test_exists_user(self, sample_user_data):
        """測試檢查用戶是否存在"""
        storage = MemoryStorage()
        crud = AutoCRUD(model=User, storage=storage, resource_name="users")

        # 創建用戶
        created_user = crud.create(sample_user_data)
        user_id = created_user["id"]

        # 測試存在的用戶
        assert crud.exists(user_id) is True

        # 測試不存在的用戶
        assert crud.exists("nonexistent-id") is False
