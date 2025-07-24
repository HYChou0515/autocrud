"""測試基本 CRUD 功能"""

from autocrud import SingleModelCRUD, MemoryStorage
from .test_models import User


class TestBasicCrud:
    """測試基本 CRUD 功能"""

    def test_create_user(self, sample_user_data):
        """測試創建用戶"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=User, storage=storage, resource_name="users")

        user_id = crud.create(sample_user_data)

        # create now returns just the ID string
        assert isinstance(user_id, str)

        # Verify the user was actually created by getting it
        created_user = crud.get(user_id)
        assert created_user is not None
        assert created_user["name"] == sample_user_data["name"]
        assert created_user["email"] == sample_user_data["email"]
        assert created_user["age"] == sample_user_data["age"]
        assert created_user["id"] == user_id

    def test_get_user(self, sample_user_data):
        """測試獲取用戶"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=User, storage=storage, resource_name="users")

        # 先創建用戶
        user_id = crud.create(sample_user_data)

        # 獲取用戶
        retrieved_user = crud.get(user_id)

        assert retrieved_user is not None
        assert retrieved_user["id"] == user_id
        assert retrieved_user["name"] == sample_user_data["name"]

    def test_get_nonexistent_user(self):
        """測試獲取不存在的用戶"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=User, storage=storage, resource_name="users")

        result = crud.get("nonexistent-id")
        assert result is None

    def test_update_user(self, sample_user_data):
        """測試更新用戶"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=User, storage=storage, resource_name="users")

        # 創建用戶
        user_id = crud.create(sample_user_data)

        # 更新用戶
        updated_data = {
            "name": "Alice Smith",
            "email": "alice.smith@example.com",
            "age": 31,
        }
        success = crud.update(user_id, updated_data)

        assert success is True

        # Verify the update by getting the user
        updated_user = crud.get(user_id)
        assert updated_user is not None
        assert updated_user["id"] == user_id
        assert updated_user["name"] == "Alice Smith"
        assert updated_user["email"] == "alice.smith@example.com"
        assert updated_user["age"] == 31

    def test_update_nonexistent_user(self, sample_user_data):
        """測試更新不存在的用戶"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=User, storage=storage, resource_name="users")

        result = crud.update("nonexistent-id", sample_user_data)
        assert result is False

    def test_delete_user(self, sample_user_data):
        """測試刪除用戶"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=User, storage=storage, resource_name="users")

        # 創建用戶
        user_id = crud.create(sample_user_data)

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
        crud = SingleModelCRUD(model=User, storage=storage, resource_name="users")

        result = crud.delete("nonexistent-id")
        assert result is False

    def test_list_all_users(self, sample_user_data):
        """測試列出所有用戶"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=User, storage=storage, resource_name="users")

        # 創建多個用戶
        user1_id = crud.create(sample_user_data)
        user2_data = {"name": "Bob", "email": "bob@example.com", "age": 25}
        user2_id = crud.create(user2_data)

        # 列出所有用戶
        all_users = crud.list_all()

        assert len(all_users) == 2

        # 提取所有用戶的 ID
        user_ids = [user["id"] for user in all_users]
        assert user1_id in user_ids
        assert user2_id in user_ids

        # 根據 ID 找到對應的用戶
        user1_from_list = next(user for user in all_users if user["id"] == user1_id)
        user2_from_list = next(user for user in all_users if user["id"] == user2_id)

        assert user1_from_list["name"] == "Alice"
        assert user2_from_list["name"] == "Bob"

    def test_exists_user(self, sample_user_data):
        """測試檢查用戶是否存在"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=User, storage=storage, resource_name="users")

        # 創建用戶
        user_id = crud.create(sample_user_data)

        # 測試存在的用戶
        assert crud.exists(user_id) is True

        # 測試不存在的用戶
        assert crud.exists("nonexistent-id") is False
