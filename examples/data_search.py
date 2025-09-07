import datetime as dt
from dataclasses import dataclass

from msgspec import UNSET

from autocrud.crud.core import AutoCRUD
from autocrud.types import (
    DataSearchOperator,
)
from autocrud.resource_manager.core import ResourceManager
from autocrud.types import DataSearchCondition, ResourceMetaSearchQuery


@dataclass
class User:
    name: str
    email: str
    age: int
    department: str


def test_basic_data_search():
    # 創建 AutoCRUD 實例
    autocrud = AutoCRUD()

    # 添加 User 模型並指定索引字段
    autocrud.add_model(
        User,
        name="users",
        indexed_fields=[
            ("name", str),
            ("email", str),
            ("age", int),
            ("department", str),
        ],
    )

    # 獲取 resource manager
    user_manager: ResourceManager[User] = autocrud.resource_managers["users"]

    # 設置用戶上下文
    current_user = "test_user"
    current_time = dt.datetime.now()

    with user_manager.meta_provide(current_user, current_time):
        # 創建一些測試用戶
        users_data = [
            User(
                name="Alice",
                email="alice@company.com",
                age=25,
                department="Engineering",
            ),
            User(name="Bob", email="bob@company.com", age=30, department="Marketing"),
            User(
                name="Charlie",
                email="charlie@external.org",
                age=35,
                department="Engineering",
            ),
            User(name="Diana", email="diana@company.com", age=28, department="Sales"),
            User(name="Eve", email="eve@company.com", age=32, department="Engineering"),
        ]

        created_resources = []
        for user_data in users_data:
            info = user_manager.create(user_data)
            created_resources.append(info)
            print(
                f"Created user: {user_data.name} with resource_id: {info.resource_id}",
            )

        # 測試 1: 搜尋特定部門的用戶
        print("\n=== Test 1: Search by department ===")
        query = ResourceMetaSearchQuery(
            data_conditions=[
                DataSearchCondition(
                    field_path="department",
                    operator=DataSearchOperator.equals,
                    value="Engineering",
                ),
            ],
            limit=10,
            offset=0,
        )

        results = user_manager.search_resources(query)
        print(f"Found {len(results)} Engineering users:")
        for meta in results:
            resource = user_manager.get_resource_revision(
                meta.resource_id,
                meta.current_revision_id,
            )
            print(f"  - {resource.data.name} ({resource.data.email})")
            # 驗證索引數據是否正確
            if meta.indexed_data is not UNSET:
                print(f"    Indexed data: {meta.indexed_data}")

        # 測試 2: 搜尋年齡範圍
        print("\n=== Test 2: Search by age range ===")
        query = ResourceMetaSearchQuery(
            data_conditions=[
                DataSearchCondition(
                    field_path="age",
                    operator=DataSearchOperator.greater_than_or_equal,
                    value=30,
                ),
            ],
            limit=10,
            offset=0,
        )

        results = user_manager.search_resources(query)
        print(f"Found {len(results)} users aged 30 or older:")
        for meta in results:
            resource = user_manager.get_resource_revision(
                meta.resource_id,
                meta.current_revision_id,
            )
            print(f"  - {resource.data.name} (age: {resource.data.age})")

        # 測試 3: 搜尋 email 包含特定域名
        print("\n=== Test 3: Search by email domain ===")
        query = ResourceMetaSearchQuery(
            data_conditions=[
                DataSearchCondition(
                    field_path="email",
                    operator=DataSearchOperator.contains,
                    value="@company.com",
                ),
            ],
            limit=10,
            offset=0,
        )

        results = user_manager.search_resources(query)
        print(f"Found {len(results)} users with @company.com email:")
        for meta in results:
            resource = user_manager.get_resource_revision(
                meta.resource_id,
                meta.current_revision_id,
            )
            print(f"  - {resource.data.name} ({resource.data.email})")

        # 測試 4: 組合條件搜尋
        print("\n=== Test 4: Combined conditions search ===")
        query = ResourceMetaSearchQuery(
            data_conditions=[
                DataSearchCondition(
                    field_path="department",
                    operator=DataSearchOperator.equals,
                    value="Engineering",
                ),
                DataSearchCondition(
                    field_path="age",
                    operator=DataSearchOperator.less_than,
                    value=35,
                ),
            ],
            limit=10,
            offset=0,
        )

        results = user_manager.search_resources(query)
        print(f"Found {len(results)} Engineering users under 35:")
        for meta in results:
            resource = user_manager.get_resource_revision(
                meta.resource_id,
                meta.current_revision_id,
            )
            print(
                f"  - {resource.data.name} (age: {resource.data.age}, dept: {resource.data.department})",
            )

        # 測試 5: 更新用戶並驗證索引更新
        print("\n=== Test 5: Update user and verify index update ===")
        if created_resources:
            first_resource_id = created_resources[0].resource_id
            original_user = user_manager.get(first_resource_id)
            print(
                f"Original user: {original_user.data.name} - {original_user.data.department}",
            )

            # 更新用戶部門
            updated_user = User(
                name=original_user.data.name,
                email=original_user.data.email,
                age=original_user.data.age,
                department="HR",  # 改變部門
            )

            user_manager.update(first_resource_id, updated_user)
            print("Updated user department to HR")

            # 驗證更新後的索引
            updated_meta = user_manager.get_meta(first_resource_id)
            if updated_meta.indexed_data is not UNSET:
                print(f"Updated indexed data: {updated_meta.indexed_data}")

            # 再次搜尋 Engineering 部門，應該少一個用戶
            query = ResourceMetaSearchQuery(
                data_conditions=[
                    DataSearchCondition(
                        field_path="department",
                        operator=DataSearchOperator.equals,
                        value="Engineering",
                    ),
                ],
                limit=10,
                offset=0,
            )

            results = user_manager.search_resources(query)
            print(f"After update, found {len(results)} Engineering users:")
            for meta in results:
                resource = user_manager.get_resource_revision(
                    meta.resource_id,
                    meta.current_revision_id,
                )
                print(f"  - {resource.data.name}")


if __name__ == "__main__":
    test_basic_data_search()
    print("\n✅ All tests completed!")
