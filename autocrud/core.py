"""AutoCRUD 核心模組"""

import uuid
from typing import Any, Dict, Type, Optional
from .converter import ModelConverter
from .storage import Storage


class AutoCRUD:
    """自動 CRUD 系統核心類"""

    def __init__(
        self,
        model: Type,
        storage: Storage,
        resource_name: str,
        id_generator: Optional[callable] = None,
    ):
        self.model = model
        self.storage = storage
        self.resource_name = resource_name
        self.converter = ModelConverter()
        self.id_generator = id_generator or (lambda: str(uuid.uuid4()))

        # 驗證模型類型
        self.model_type = self.converter.detect_model_type(model)
        self.model_fields = self.converter.extract_fields(model)

    def _make_key(self, resource_id: str) -> str:
        """生成存儲鍵"""
        return f"{self.resource_name}:{resource_id}"

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """創建資源"""
        # 生成 ID
        resource_id = self.id_generator()

        # 創建模型實例
        instance = self.converter.from_dict(self.model, data)

        # 轉換為字典並添加 ID
        instance_dict = self.converter.to_dict(instance)
        instance_dict["id"] = resource_id

        # 存儲
        key = self._make_key(resource_id)
        self.storage.set(key, instance_dict)

        return instance_dict

    def get(self, resource_id: str) -> Optional[Dict[str, Any]]:
        """獲取資源"""
        key = self._make_key(resource_id)
        return self.storage.get(key)

    def update(
        self, resource_id: str, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """更新資源"""
        key = self._make_key(resource_id)

        # 檢查資源是否存在
        if not self.storage.exists(key):
            return None

        # 創建模型實例驗證數據
        instance = self.converter.from_dict(self.model, data)

        # 轉換為字典並保持 ID
        instance_dict = self.converter.to_dict(instance)
        instance_dict["id"] = resource_id

        # 更新存儲
        self.storage.set(key, instance_dict)

        return instance_dict

    def delete(self, resource_id: str) -> bool:
        """刪除資源"""
        key = self._make_key(resource_id)
        return self.storage.delete(key)

    def exists(self, resource_id: str) -> bool:
        """檢查資源是否存在"""
        key = self._make_key(resource_id)
        return self.storage.exists(key)

    def list_all(self) -> Dict[str, Dict[str, Any]]:
        """列出所有資源"""
        prefix = f"{self.resource_name}:"
        all_keys = self.storage.list_keys()

        result = {}
        for key in all_keys:
            if key.startswith(prefix):
                resource_id = key[len(prefix) :]
                data = self.storage.get(key)
                if data:
                    result[resource_id] = data

        return result

    def create_fastapi_app(self, **kwargs):
        """創建 FastAPI 應用的便利方法"""
        from .fastapi_generator import FastAPIGenerator

        generator = FastAPIGenerator(self)
        return generator.create_fastapi_app(**kwargs)


# 使用範例
if __name__ == "__main__":
    from dataclasses import dataclass
    from .storage import MemoryStorage

    @dataclass
    class User:
        name: str
        email: str
        age: int

    # 創建 AutoCRUD 實例
    storage = MemoryStorage()
    crud = AutoCRUD(model=User, storage=storage, resource_name="users")

    # 測試創建
    user_data = {"name": "Alice", "email": "alice@example.com", "age": 30}
    created_user = crud.create(user_data)
    print(f"創建用戶: {created_user}")

    # 測試獲取
    user_id = created_user["id"]
    retrieved_user = crud.get(user_id)
    print(f"獲取用戶: {retrieved_user}")

    # 測試更新
    updated_data = {
        "name": "Alice Smith",
        "email": "alice.smith@example.com",
        "age": 31,
    }
    updated_user = crud.update(user_id, updated_data)
    print(f"更新用戶: {updated_user}")

    # 測試列出所有
    all_users = crud.list_all()
    print(f"所有用戶: {all_users}")

    # 測試刪除
    deleted = crud.delete(user_id)
    print(f"刪除成功: {deleted}")
    print(f"刪除後存在: {crud.exists(user_id)}")
