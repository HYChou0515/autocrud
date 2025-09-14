import datetime as dt
from dataclasses import dataclass

import pytest
from msgspec import UNSET

from autocrud.crud.core import AutoCRUD
from autocrud.types import (
    DataSearchOperator,
    RevisionInfo,
)
from autocrud.resource_manager.core import ResourceManager
from autocrud.resource_manager.storage_factory import MemoryStorageFactory
from autocrud.types import DataSearchCondition, ResourceMetaSearchQuery


@dataclass
class User:
    name: str
    email: str
    age: int
    department: str


class TestAutoCRUDDataSearch:
    """High-level tests for AutoCRUD data search functionality."""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Setup AutoCRUD with User model and create test data."""
        # 創建 AutoCRUD 實例
        self.autocrud = AutoCRUD(
            storage_factory=MemoryStorageFactory(),
        )

        # 添加 User 模型並指定索引字段
        self.autocrud.add_model(
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
        self.user_manager: ResourceManager[User] = self.autocrud.resource_managers[
            "users"
        ]

        # 設置用戶上下文
        self.current_user = "test_user"
        self.current_time = dt.datetime.now()

        # 創建測試用戶
        self.users_data = [
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

        self.created_resources: list[RevisionInfo] = []
        with self.user_manager.meta_provide(self.current_user, self.current_time):
            for user_data in self.users_data:
                info = self.user_manager.create(user_data)
                self.created_resources.append(info)

    def test_search_by_department(self):
        """測試按部門搜尋用戶。"""
        with self.user_manager.meta_provide(self.current_user, self.current_time):
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

            results = self.user_manager.search_resources(query)

            # 應該找到 3 個 Engineering 用戶 (Alice, Charlie, Eve)
            assert len(results) == 3

            engineering_names = set()
            for meta in results:
                resource = self.user_manager.get_resource_revision(
                    meta.resource_id,
                    meta.current_revision_id,
                )
                engineering_names.add(resource.data.name)

                # 驗證索引數據是否正確
                assert meta.indexed_data is not UNSET
                assert meta.indexed_data["department"] == "Engineering"

            assert engineering_names == {"Alice", "Charlie", "Eve"}

    def test_search_by_age_range(self):
        """測試按年齡範圍搜尋用戶。"""
        with self.user_manager.meta_provide(self.current_user, self.current_time):
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

            results = self.user_manager.search_resources(query)

            # 應該找到 3 個年齡 >= 30 的用戶 (Bob: 30, Charlie: 35, Eve: 32)
            assert len(results) == 3

            ages = []
            for meta in results:
                resource = self.user_manager.get_resource_revision(
                    meta.resource_id,
                    meta.current_revision_id,
                )
                ages.append(resource.data.age)
                assert resource.data.age >= 30

            assert sorted(ages) == [30, 32, 35]

    def test_search_by_email_domain(self):
        """測試按 email 域名搜尋用戶。"""
        with self.user_manager.meta_provide(self.current_user, self.current_time):
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

            results = self.user_manager.search_resources(query)

            # 應該找到 4 個 @company.com 的用戶 (Alice, Bob, Diana, Eve)
            assert len(results) == 4

            company_users = set()
            for meta in results:
                resource = self.user_manager.get_resource_revision(
                    meta.resource_id,
                    meta.current_revision_id,
                )
                company_users.add(resource.data.name)
                assert "@company.com" in resource.data.email

            assert company_users == {"Alice", "Bob", "Diana", "Eve"}

    def test_search_with_combined_conditions(self):
        """測試組合條件搜尋。"""
        with self.user_manager.meta_provide(self.current_user, self.current_time):
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

            results = self.user_manager.search_resources(query)

            # 應該找到 2 個年齡 < 35 的 Engineering 用戶 (Alice: 25, Eve: 32)
            assert len(results) == 2

            engineering_under_35 = set()
            for meta in results:
                resource = self.user_manager.get_resource_revision(
                    meta.resource_id,
                    meta.current_revision_id,
                )
                engineering_under_35.add(resource.data.name)
                assert resource.data.department == "Engineering"
                assert resource.data.age < 35

            assert engineering_under_35 == {"Alice", "Eve"}

    def test_update_user_and_verify_index_update(self):
        """測試更新用戶並驗證索引更新。"""
        with self.user_manager.meta_provide(self.current_user, self.current_time):
            # 獲取第一個用戶
            first_resource_id = self.created_resources[0].resource_id
            original_user = self.user_manager.get(first_resource_id)

            assert original_user.data.name == "Alice"
            assert original_user.data.department == "Engineering"

            # 更新用戶部門
            updated_user = User(
                name=original_user.data.name,
                email=original_user.data.email,
                age=original_user.data.age,
                department="HR",  # 改變部門
            )

            self.user_manager.update(first_resource_id, updated_user)

            # 驗證更新後的索引
            updated_meta = self.user_manager.get_meta(first_resource_id)
            assert updated_meta.indexed_data is not UNSET
            assert updated_meta.indexed_data["department"] == "HR"

            # 再次搜尋 Engineering 部門，應該只剩 2 個用戶 (Charlie, Eve)
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

            results = self.user_manager.search_resources(query)
            assert len(results) == 2  # Alice 已經被移出 Engineering 部門

            remaining_engineering = set()
            for meta in results:
                resource = self.user_manager.get_resource_revision(
                    meta.resource_id,
                    meta.current_revision_id,
                )
                remaining_engineering.add(resource.data.name)

            assert remaining_engineering == {"Charlie", "Eve"}

    def test_search_with_pagination(self):
        """測試分頁功能。"""
        with self.user_manager.meta_provide(self.current_user, self.current_time):
            # 搜尋所有用戶，限制每頁 2 個
            query = ResourceMetaSearchQuery(
                limit=2,
                offset=0,
            )

            first_page = self.user_manager.search_resources(query)
            assert len(first_page) == 2

            # 搜尋第二頁
            query = ResourceMetaSearchQuery(
                limit=2,
                offset=2,
            )

            second_page = self.user_manager.search_resources(query)
            assert len(second_page) == 2

            # 搜尋第三頁
            query = ResourceMetaSearchQuery(
                limit=2,
                offset=4,
            )

            third_page = self.user_manager.search_resources(query)
            assert len(third_page) == 1  # 只剩下最後一個用戶

            # 確保沒有重複的用戶
            all_resource_ids = set()
            for page in [first_page, second_page, third_page]:
                for meta in page:
                    assert meta.resource_id not in all_resource_ids
                    all_resource_ids.add(meta.resource_id)

            assert len(all_resource_ids) == 5  # 總共 5 個用戶

    def test_search_empty_results(self):
        """測試搜尋無結果的情況。"""
        with self.user_manager.meta_provide(self.current_user, self.current_time):
            query = ResourceMetaSearchQuery(
                data_conditions=[
                    DataSearchCondition(
                        field_path="department",
                        operator=DataSearchOperator.equals,
                        value="NonExistentDepartment",
                    ),
                ],
                limit=10,
                offset=0,
            )

            results = self.user_manager.search_resources(query)
            assert len(results) == 0
            assert isinstance(results, list)

    def test_indexed_data_consistency(self):
        """測試索引數據的一致性。"""
        with self.user_manager.meta_provide(self.current_user, self.current_time):
            # 獲取所有用戶的 meta
            for resource_info in self.created_resources:
                meta = self.user_manager.get_meta(resource_info.resource_id)
                resource = self.user_manager.get(resource_info.resource_id)

                # 驗證索引數據與實際數據一致
                assert meta.indexed_data is not UNSET
                assert meta.indexed_data["name"] == resource.data.name
                assert meta.indexed_data["email"] == resource.data.email
                assert meta.indexed_data["age"] == resource.data.age
                assert meta.indexed_data["department"] == resource.data.department
