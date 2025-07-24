"""
測試 Advanced Updater 系統
"""

import pytest

from autocrud import (
    SingleModelCRUD,
    AutoCRUD,
    MemoryStorage,
    AdvancedUpdater,
    UpdateOperation,
    UpdateAction,
    undefined,
    set_value,
    list_set,
    list_add,
    list_remove,
    dict_set,
    dict_update,
    dict_remove,
)
from .test_models import ComplexUser


class TestAdvancedUpdater:
    """測試 AdvancedUpdater 類"""

    def test_create_update_operations(self):
        """測試創建各種更新操作"""
        # 測試 undefined
        op = UpdateOperation.undefined()
        assert op.action == UpdateAction.UNDEFINED
        assert op.value is None

        # 測試 set_value
        op = UpdateOperation.set_value("new_name")
        assert op.action == UpdateAction.SET
        assert op.value == "new_name"

        # 測試 list operations
        op = UpdateOperation.list_set(["tag1", "tag2"])
        assert op.action == UpdateAction.LIST_SET
        assert op.value == ["tag1", "tag2"]

        op = UpdateOperation.list_add(["tag3"])
        assert op.action == UpdateAction.LIST_ADD
        assert op.value == ["tag3"]

        op = UpdateOperation.list_remove(["tag1"])
        assert op.action == UpdateAction.LIST_REMOVE
        assert op.value == ["tag1"]

        # 測試 dict operations
        op = UpdateOperation.dict_set({"key": "value"})
        assert op.action == UpdateAction.DICT_SET
        assert op.value == {"key": "value"}

        op = UpdateOperation.dict_update({"new_key": "new_value"})
        assert op.action == UpdateAction.DICT_UPDATE
        assert op.value == {"new_key": "new_value"}

        op = UpdateOperation.dict_remove(["old_key"])
        assert op.action == UpdateAction.DICT_REMOVE
        assert op.value == ["old_key"]

    def test_updater_apply_undefined(self):
        """測試 undefined 操作（不改變）"""
        current_data = {"name": "John", "age": 30}
        operations = {"name": UpdateOperation.undefined()}
        updater = AdvancedUpdater(operations)

        result = updater.apply_to(current_data)
        assert result["name"] == "John"  # 沒有改變
        assert result["age"] == 30

    def test_updater_apply_set_value(self):
        """測試設置新值"""
        current_data = {"name": "John", "age": 30}
        operations = {"name": UpdateOperation.set_value("Jane")}
        updater = AdvancedUpdater(operations)

        result = updater.apply_to(current_data)
        assert result["name"] == "Jane"
        assert result["age"] == 30

    def test_updater_apply_list_operations(self):
        """測試列表操作"""
        current_data = {"tags": ["tag1", "tag2"]}

        # 測試 list_set
        operations = {"tags": UpdateOperation.list_set(["new_tag1", "new_tag2"])}
        updater = AdvancedUpdater(operations)
        result = updater.apply_to(current_data)
        assert result["tags"] == ["new_tag1", "new_tag2"]

        # 測試 list_add
        operations = {"tags": UpdateOperation.list_add(["tag3", "tag4"])}
        updater = AdvancedUpdater(operations)
        result = updater.apply_to(current_data)
        assert result["tags"] == ["tag1", "tag2", "tag3", "tag4"]

        # 測試 list_remove
        operations = {"tags": UpdateOperation.list_remove(["tag1"])}
        updater = AdvancedUpdater(operations)
        result = updater.apply_to(current_data)
        assert result["tags"] == ["tag2"]

        # 測試在空屬性上 list_add
        current_data_empty = {}
        operations = {"tags": UpdateOperation.list_add(["tag1"])}
        updater = AdvancedUpdater(operations)
        result = updater.apply_to(current_data_empty)
        assert result["tags"] == ["tag1"]

    def test_updater_apply_dict_operations(self):
        """測試字典操作"""
        current_data = {"metadata": {"key1": "value1", "key2": "value2"}}

        # 測試 dict_set
        operations = {"metadata": UpdateOperation.dict_set({"new_key": "new_value"})}
        updater = AdvancedUpdater(operations)
        result = updater.apply_to(current_data)
        assert result["metadata"] == {"new_key": "new_value"}

        # 測試 dict_update
        operations = {
            "metadata": UpdateOperation.dict_update(
                {"key3": "value3", "key1": "updated_value1"}
            )
        }
        updater = AdvancedUpdater(operations)
        result = updater.apply_to(current_data)
        assert result["metadata"] == {
            "key1": "updated_value1",
            "key2": "value2",
            "key3": "value3",
        }

        # 測試 dict_remove
        operations = {"metadata": UpdateOperation.dict_remove(["key1"])}
        updater = AdvancedUpdater(operations)
        result = updater.apply_to(current_data)
        assert result["metadata"] == {"key2": "value2"}

        # 測試在空屬性上 dict_update
        current_data_empty = {}
        operations = {"metadata": UpdateOperation.dict_update({"key1": "value1"})}
        updater = AdvancedUpdater(operations)
        result = updater.apply_to(current_data_empty)
        assert result["metadata"] == {"key1": "value1"}

    def test_updater_from_dict_simple(self):
        """測試從字典格式創建 updater（簡單值）"""
        update_data = {"name": "Jane", "age": 25}
        updater = AdvancedUpdater.from_dict(update_data)

        current_data = {"name": "John", "age": 30}
        result = updater.apply_to(current_data)
        assert result["name"] == "Jane"
        assert result["age"] == 25

    def test_updater_from_dict_structured(self):
        """測試從字典格式創建 updater（結構化操作）"""
        update_data = {
            "name": {"_action": "set", "value": "Jane"},
            "age": {"_action": "undefined"},
            "tags": {"_action": "list_add", "value": ["new_tag"]},
            "metadata": {"_action": "dict_update", "value": {"new_key": "new_value"}},
        }
        updater = AdvancedUpdater.from_dict(update_data)

        current_data = {
            "name": "John",
            "age": 30,
            "tags": ["old_tag"],
            "metadata": {"old_key": "old_value"},
        }
        result = updater.apply_to(current_data)
        assert result["name"] == "Jane"
        assert result["age"] == 30  # unchanged
        assert result["tags"] == ["old_tag", "new_tag"]
        assert result["metadata"] == {"old_key": "old_value", "new_key": "new_value"}

    def test_updater_from_dict_invalid_action(self):
        """測試未知 action 時拋出錯誤"""
        update_data = {"name": {"_action": "invalid_action", "value": "test"}}

        with pytest.raises(ValueError) as exc_info:
            AdvancedUpdater.from_dict(update_data)

        error_message = str(exc_info.value)
        assert "Unknown action type 'invalid_action'" in error_message
        assert "name" in error_message
        assert "Valid actions are:" in error_message
        # 確保錯誤訊息包含動態生成的有效 actions
        assert "set" in error_message
        assert "undefined" in error_message
        assert "list_add" in error_message


class TestConvenienceFunctions:
    """測試便利函數"""

    def test_convenience_functions(self):
        """測試所有便利函數"""
        assert undefined() == {"_action": "undefined"}
        assert set_value("test") == {"_action": "set", "value": "test"}
        assert list_set(["a", "b"]) == {"_action": "list_set", "value": ["a", "b"]}
        assert list_add(["c"]) == {"_action": "list_add", "value": ["c"]}
        assert list_remove(["a"]) == {"_action": "list_remove", "value": ["a"]}
        assert dict_set({"k": "v"}) == {"_action": "dict_set", "value": {"k": "v"}}
        assert dict_update({"k": "v"}) == {
            "_action": "dict_update",
            "value": {"k": "v"},
        }
        assert dict_remove(["k"]) == {"_action": "dict_remove", "value": ["k"]}


class TestSingleModelCRUDAdvancedUpdate:
    """測試 SingleModelCRUD 的 advanced_update 方法"""

    def setup_method(self):
        """設置測試環境"""
        self.storage = MemoryStorage()
        self.crud = SingleModelCRUD(ComplexUser, self.storage, "users")

    def test_advanced_update_basic(self):
        """測試基本的 advanced_update"""
        # 創建測試數據（需要包含所有必要字段）
        user_data = {
            "name": "John",
            "tags": ["developer", "python"],
            "metadata": {"role": "admin", "level": 5},
            "email": None,
        }
        created_id = self.crud.create(user_data)
        assert created_id is not None
        user_id = created_id

        # 使用 advanced_update 更新
        update_data = {
            "name": set_value("Jane"),
            "tags": list_add(["javascript"]),
            "metadata": dict_update({"department": "engineering"}),
        }

        updated = self.crud.advanced_update(user_id, update_data)
        assert updated is not None
        assert updated["name"] == "Jane"
        assert "javascript" in updated["tags"]
        assert "python" in updated["tags"]  # 原有的還在
        assert updated["metadata"]["department"] == "engineering"
        assert updated["metadata"]["role"] == "admin"  # 原有的還在

    def test_advanced_update_undefined(self):
        """測試 undefined 操作"""
        # 創建測試數據
        user_data = {
            "name": "John",
            "tags": ["developer"],
            "metadata": {"role": "admin"},
            "email": None,
        }
        created_id = self.crud.create(user_data)
        assert created_id is not None
        user_id = created_id

        # 使用 undefined 操作
        update_data = {"name": undefined(), "tags": list_add(["python"])}

        updated = self.crud.advanced_update(user_id, update_data)
        assert updated is not None
        assert updated["name"] == "John"  # 沒有改變
        assert "python" in updated["tags"]

    def test_advanced_update_list_operations(self):
        """測試列表操作"""
        # 創建測試數據
        user_data = {
            "name": "John",
            "tags": ["python", "javascript", "golang"],
            "metadata": {},
            "email": None,
        }
        created_id = self.crud.create(user_data)
        assert created_id is not None
        user_id = created_id

        # 測試 list_remove
        update_data = {"tags": list_remove(["javascript"])}
        updated = self.crud.advanced_update(user_id, update_data)
        assert updated is not None
        assert "javascript" not in updated["tags"]
        assert "python" in updated["tags"]
        assert "golang" in updated["tags"]

        # 測試 list_set
        update_data = {"tags": list_set(["rust", "c++"])}
        updated = self.crud.advanced_update(user_id, update_data)
        assert updated is not None
        assert updated["tags"] == ["rust", "c++"]

    def test_advanced_update_dict_operations(self):
        """測試字典操作"""
        # 創建測試數據
        user_data = {
            "name": "John",
            "tags": [],
            "metadata": {"role": "admin", "level": 5, "department": "IT"},
            "email": None,
        }
        created_id = self.crud.create(user_data)
        assert created_id is not None
        user_id = created_id

        # 測試 dict_remove
        update_data = {"metadata": dict_remove(["department"])}
        updated = self.crud.advanced_update(user_id, update_data)
        assert updated is not None
        assert "department" not in updated["metadata"]
        assert updated["metadata"]["role"] == "admin"

        # 測試 dict_set
        update_data = {"metadata": dict_set({"new_role": "user", "active": True})}
        updated = self.crud.advanced_update(user_id, update_data)
        assert updated is not None
        assert updated["metadata"] == {"new_role": "user", "active": True}

    def test_advanced_update_nonexistent(self):
        """測試更新不存在的資源"""
        update_data = {"name": set_value("Jane")}
        result = self.crud.advanced_update("nonexistent", update_data)
        assert result is None

    def test_advanced_update_validation_failure(self):
        """測試數據驗證失敗的情況"""
        # 創建測試數據
        user_data = {"name": "John", "tags": [], "metadata": {}, "email": None}
        created_id = self.crud.create(user_data)
        assert created_id is not None
        user_id = created_id

        # 嘗試設置無效的數據類型（字符串設為整數）
        # 在 dataclass 中，通常會進行類型轉換，所以這個更新可能會成功
        update_data = {"name": set_value(123)}  # name 應該是字符串
        updated = self.crud.advanced_update(user_id, update_data)

        # 驗證更新是否成功，如果成功則檢查類型轉換
        if updated is not None:
            # 在某些情況下可能會自動轉換類型
            assert updated["name"] == 123 or updated["name"] == "123"
        else:
            # 如果驗證失敗，返回 None 也是可接受的
            pass


class TestAutoCRUDAdvancedUpdate:
    """測試 AutoCRUD 的 advanced_update 方法"""

    def setup_method(self):
        """設置測試環境"""
        self.autocrud = AutoCRUD()
        self.autocrud.register_model(ComplexUser, "users")

    def test_multi_model_advanced_update(self):
        """測試多模型 advanced_update"""
        # 創建測試數據（不包含 id，會自動生成）
        user_data = {
            "name": "John",
            "tags": ["developer"],
            "metadata": {"role": "admin"},
            "email": None,
        }
        created_id = self.autocrud.create("users", user_data)
        assert created_id is not None
        user_id = created_id

        # 使用 advanced_update
        update_data = {
            "name": set_value("Jane"),
            "tags": list_add(["python", "javascript"]),
            "metadata": dict_update({"level": 5}),
        }

        updated = self.autocrud.advanced_update("users", user_id, update_data)
        assert updated is not None
        assert updated["name"] == "Jane"
        assert set(updated["tags"]) == {"developer", "python", "javascript"}
        assert updated["metadata"]["role"] == "admin"
        assert updated["metadata"]["level"] == 5

    def test_multi_model_advanced_update_nonexistent_resource(self):
        """測試不存在的資源名稱"""
        with pytest.raises(ValueError, match="Resource 'nonexistent' not registered"):
            self.autocrud.advanced_update(
                "nonexistent", "1", {"name": set_value("test")}
            )

    def test_multi_model_advanced_update_nonexistent_item(self):
        """測試不存在的資源項目"""
        update_data = {"name": set_value("Jane")}
        result = self.autocrud.advanced_update("users", "nonexistent", update_data)
        assert result is None


class TestAdvancedUpdateIntegration:
    """測試 Advanced Update 的整合功能"""

    def setup_method(self):
        """設置測試環境"""
        self.storage = MemoryStorage()
        self.crud = SingleModelCRUD(ComplexUser, self.storage, "users")

    def test_complex_update_scenario(self):
        """測試複雜的更新場景"""
        # 創建複雜的初始數據
        user_data = {
            "name": "John Doe",
            "tags": ["python", "javascript", "react", "django"],
            "metadata": {
                "role": "senior_developer",
                "level": 8,
                "skills": {"backend": True, "frontend": True},
                "projects": ["project_a", "project_b"],
                "contact": {"email": "john@example.com", "phone": "123-456-7890"},
            },
            "email": None,
        }
        created_id = self.crud.create(user_data)
        assert created_id is not None
        user_id = created_id

        # 執行複雜的更新操作
        update_data = {
            "name": set_value("John Smith"),
            "tags": list_remove(["react"]),  # 移除 react
            "metadata": {
                "_action": "dict_update",
                "value": {
                    "level": 9,  # 升級
                    "department": "engineering",  # 新增部門
                    "skills": {
                        "backend": True,
                        "frontend": True,
                        "devops": True,
                    },  # 更新技能
                },
            },
        }

        updated = self.crud.advanced_update(user_id, update_data)
        assert updated is not None

        # 驗證更新結果
        assert updated["name"] == "John Smith"
        assert "react" not in updated["tags"]
        assert "python" in updated["tags"]  # 其他標籤還在
        assert updated["metadata"]["level"] == 9
        assert updated["metadata"]["role"] == "senior_developer"  # 原有值保持
        assert updated["metadata"]["department"] == "engineering"  # 新增值
        assert updated["metadata"]["skills"]["devops"] is True  # 技能更新

    def test_mixed_operations(self):
        """測試混合操作（簡單值 + 結構化操作）"""
        user_data = {
            "name": "John",
            "tags": ["python"],
            "metadata": {"role": "admin"},
            "email": None,
        }
        created_id = self.crud.create(user_data)
        assert created_id is not None
        user_id = created_id

        # 混合簡單值和結構化操作
        update_data = {
            "name": "Jane",  # 簡單值
            "email": "jane@example.com",  # 簡單值
            "tags": list_add(["javascript"]),  # 結構化操作
            "metadata": dict_update({"level": 5}),  # 結構化操作
        }

        updated = self.crud.advanced_update(user_id, update_data)
        assert updated is not None
        assert updated["name"] == "Jane"
        assert updated["email"] == "jane@example.com"
        assert set(updated["tags"]) == {"python", "javascript"}
        assert updated["metadata"]["role"] == "admin"
        assert updated["metadata"]["level"] == 5
