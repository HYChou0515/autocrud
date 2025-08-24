import datetime as dt
from dataclasses import dataclass
import pytest
from autocrud.crud.core import AutoCRUD, MemoryStorageFactory
from autocrud.resource_manager.basic import (
    IndexableField,
    DataSearchCondition,
    DataSearchOperator,
    ResourceMetaSearchQuery,
)
from msgspec import UNSET

from autocrud.resource_manager.core import ResourceManager


@dataclass
class User:
    name: str
    email: str
    age: int
    department: str


@dataclass
class Product:
    name: str
    price: float
    category: str
    tags: list[str]


class TestDataSearch:
    """Test data search functionality with indexed fields."""

    @pytest.fixture
    def autocrud_with_users(self):
        """Create AutoCRUD instance with User model and indexed fields."""
        autocrud = AutoCRUD()

        # 定義要索引的字段
        indexed_fields = [
            IndexableField(field_path="name", field_type=str),
            IndexableField(field_path="email", field_type=str),
            IndexableField(field_path="age", field_type=int),
            IndexableField(field_path="department", field_type=str),
        ]

        # 添加 User 模型並指定索引字段
        autocrud.add_model(
            User,
            name="users",
            storage_factory=MemoryStorageFactory(),
            indexed_fields=indexed_fields,
        )

        return autocrud

    @pytest.fixture
    def sample_users(self):
        """Create sample user data for testing."""
        return [
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

    def test_basic_department_search(self, autocrud_with_users, sample_users):
        """Test searching by department field."""
        autocrud = autocrud_with_users
        user_manager: ResourceManager[User] = autocrud.resource_managers["users"]

        current_user = "test_user"
        current_time = dt.datetime.now()

        with user_manager.meta_provide(current_user, current_time):
            # Create test users
            created_resources = []
            for user_data in sample_users:
                info = user_manager.create(user_data)
                created_resources.append(info)

            # Search for Engineering department users
            query = ResourceMetaSearchQuery(
                data_conditions=[
                    DataSearchCondition(
                        field_path="department",
                        operator=DataSearchOperator.equals,
                        value="Engineering",
                    )
                ],
                limit=10,
                offset=0,
            )

            results = user_manager.search_resources(query)

            # Should find 3 Engineering users (Alice, Charlie, Eve)
            assert len(results) == 3

            engineering_names = set()
            for meta in results:
                resource = user_manager.get_resource_revision(
                    meta.resource_id, meta.current_revision_id
                )
                engineering_names.add(resource.data.name)

                # Verify indexed data is populated
                assert meta.indexed_data is not UNSET
                assert meta.indexed_data["department"] == "Engineering"

            assert engineering_names == {"Alice", "Charlie", "Eve"}

    def test_age_range_search(self, autocrud_with_users, sample_users):
        """Test searching by age range."""
        autocrud = autocrud_with_users
        user_manager: ResourceManager[User] = autocrud.resource_managers["users"]

        current_user = "test_user"
        current_time = dt.datetime.now()

        with user_manager.meta_provide(current_user, current_time):
            # Create test users
            for user_data in sample_users:
                user_manager.create(user_data)

            # Search for users aged 30 or older
            query = ResourceMetaSearchQuery(
                data_conditions=[
                    DataSearchCondition(
                        field_path="age",
                        operator=DataSearchOperator.greater_than_or_equal,
                        value=30,
                    )
                ],
                limit=10,
                offset=0,
            )

            results = user_manager.search_resources(query)

            # Should find 3 users (Bob: 30, Charlie: 35, Eve: 32)
            assert len(results) == 3

            ages = []
            for meta in results:
                resource = user_manager.get_resource_revision(
                    meta.resource_id, meta.current_revision_id
                )
                ages.append(resource.data.age)
                assert resource.data.age >= 30

            assert set(ages) == {30, 32, 35}

    def test_email_domain_search(self, autocrud_with_users, sample_users):
        """Test searching by email domain using contains operator."""
        autocrud = autocrud_with_users
        user_manager: ResourceManager[User] = autocrud.resource_managers["users"]

        current_user = "test_user"
        current_time = dt.datetime.now()

        with user_manager.meta_provide(current_user, current_time):
            # Create test users
            for user_data in sample_users:
                user_manager.create(user_data)

            # Search for users with @company.com email
            query = ResourceMetaSearchQuery(
                data_conditions=[
                    DataSearchCondition(
                        field_path="email",
                        operator=DataSearchOperator.contains,
                        value="@company.com",
                    )
                ],
                limit=10,
                offset=0,
            )

            results = user_manager.search_resources(query)

            # Should find 4 users (all except Charlie who has @external.org)
            assert len(results) == 4

            company_emails = set()
            for meta in results:
                resource = user_manager.get_resource_revision(
                    meta.resource_id, meta.current_revision_id
                )
                company_emails.add(resource.data.email)
                assert "@company.com" in resource.data.email

            expected_emails = {
                "alice@company.com",
                "bob@company.com",
                "diana@company.com",
                "eve@company.com",
            }
            assert company_emails == expected_emails

    def test_combined_conditions_search(self, autocrud_with_users, sample_users):
        """Test searching with multiple combined conditions."""
        autocrud = autocrud_with_users
        user_manager: ResourceManager[User] = autocrud.resource_managers["users"]

        current_user = "test_user"
        current_time = dt.datetime.now()

        with user_manager.meta_provide(current_user, current_time):
            # Create test users
            for user_data in sample_users:
                user_manager.create(user_data)

            # Search for Engineering users under 35 years old
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

            # Should find 2 users (Alice: 25, Eve: 32) - Charlie is 35 so excluded
            assert len(results) == 2

            engineering_under_35 = set()
            for meta in results:
                resource = user_manager.get_resource_revision(
                    meta.resource_id, meta.current_revision_id
                )
                engineering_under_35.add(resource.data.name)
                assert resource.data.department == "Engineering"
                assert resource.data.age < 35

            assert engineering_under_35 == {"Alice", "Eve"}

    def test_update_and_index_maintenance(self, autocrud_with_users, sample_users):
        """Test that index is updated when resource data is modified."""
        autocrud = autocrud_with_users
        user_manager: ResourceManager[User] = autocrud.resource_managers["users"]

        current_user = "test_user"
        current_time = dt.datetime.now()

        with user_manager.meta_provide(current_user, current_time):
            # Create test users
            created_resources = []
            for user_data in sample_users:
                info = user_manager.create(user_data)
                created_resources.append(info)

            # Verify initial state - should have 3 Engineering users
            query = ResourceMetaSearchQuery(
                data_conditions=[
                    DataSearchCondition(
                        field_path="department",
                        operator=DataSearchOperator.equals,
                        value="Engineering",
                    )
                ],
                limit=10,
                offset=0,
            )

            initial_results = user_manager.search_resources(query)
            assert len(initial_results) == 3

            # Update Alice's department from Engineering to HR
            first_resource_id = created_resources[0].resource_id  # Alice
            original_user = user_manager.get(first_resource_id)
            assert original_user.data.name == "Alice"
            assert original_user.data.department == "Engineering"

            # Update user department
            updated_user = User(
                name=original_user.data.name,
                email=original_user.data.email,
                age=original_user.data.age,
                department="HR",  # Change department
            )

            user_manager.update(first_resource_id, updated_user)

            # Verify index was updated
            updated_meta = user_manager.get_meta(first_resource_id)
            assert updated_meta.indexed_data is not UNSET
            assert updated_meta.indexed_data["department"] == "HR"

            # Search again for Engineering users - should now find only 2
            updated_results = user_manager.search_resources(query)
            assert len(updated_results) == 2

            remaining_engineering_names = set()
            for meta in updated_results:
                resource = user_manager.get_resource_revision(
                    meta.resource_id, meta.current_revision_id
                )
                remaining_engineering_names.add(resource.data.name)

            # Alice should no longer be in Engineering department
            assert remaining_engineering_names == {"Charlie", "Eve"}

    def test_no_indexed_fields(self):
        """Test behavior when no indexed fields are specified."""
        autocrud = AutoCRUD()

        # Add model without indexed fields
        autocrud.add_model(
            User,
            name="users_no_index",
            storage_factory=MemoryStorageFactory(),
            # No indexed_fields parameter
        )

        user_manager: ResourceManager[User] = autocrud.resource_managers[
            "users_no_index"
        ]

        current_user = "test_user"
        current_time = dt.datetime.now()

        with user_manager.meta_provide(current_user, current_time):
            # Create a user
            user_data = User(
                name="Alice",
                email="alice@company.com",
                age=25,
                department="Engineering",
            )
            user_manager.create(user_data)

            # Try to search with data conditions - should find no results
            query = ResourceMetaSearchQuery(
                data_conditions=[
                    DataSearchCondition(
                        field_path="department",
                        operator=DataSearchOperator.equals,
                        value="Engineering",
                    )
                ],
                limit=10,
                offset=0,
            )

            results = user_manager.search_resources(query)
            # Should find no results because no indexed fields are defined
            assert len(results) == 0

    def test_different_operators(self, autocrud_with_users):
        """Test different search operators."""
        autocrud = autocrud_with_users
        user_manager: ResourceManager[User] = autocrud.resource_managers["users"]

        current_user = "test_user"
        current_time = dt.datetime.now()

        with user_manager.meta_provide(current_user, current_time):
            # Create test users with various ages
            test_users = [
                User(name="User1", email="user1@test.com", age=20, department="Dept1"),
                User(name="User2", email="user2@test.com", age=25, department="Dept2"),
                User(name="User3", email="user3@test.com", age=30, department="Dept3"),
                User(name="User4", email="user4@test.com", age=35, department="Dept4"),
            ]

            for user_data in test_users:
                user_manager.create(user_data)

            # Test not_equals operator
            query = ResourceMetaSearchQuery(
                data_conditions=[
                    DataSearchCondition(
                        field_path="age",
                        operator=DataSearchOperator.not_equals,
                        value=25,
                    )
                ],
            )
            results = user_manager.search_resources(query)
            assert len(results) == 3  # All except User2 (age 25)

            # Test greater_than operator
            query = ResourceMetaSearchQuery(
                data_conditions=[
                    DataSearchCondition(
                        field_path="age",
                        operator=DataSearchOperator.greater_than,
                        value=25,
                    )
                ],
            )
            results = user_manager.search_resources(query)
            assert len(results) == 2  # User3 (30) and User4 (35)

            # Test less_than_or_equal operator
            query = ResourceMetaSearchQuery(
                data_conditions=[
                    DataSearchCondition(
                        field_path="age",
                        operator=DataSearchOperator.less_than_or_equal,
                        value=25,
                    )
                ],
            )
            results = user_manager.search_resources(query)
            assert len(results) == 2  # User1 (20) and User2 (25)

            # Test starts_with operator
            query = ResourceMetaSearchQuery(
                data_conditions=[
                    DataSearchCondition(
                        field_path="email",
                        operator=DataSearchOperator.starts_with,
                        value="user1",
                    )
                ],
            )
            results = user_manager.search_resources(query)
            assert len(results) == 1  # Only user1@test.com

            # Test ends_with operator
            query = ResourceMetaSearchQuery(
                data_conditions=[
                    DataSearchCondition(
                        field_path="email",
                        operator=DataSearchOperator.ends_with,
                        value="@test.com",
                    )
                ],
            )
            results = user_manager.search_resources(query)
            assert len(results) == 4  # All users

    def test_in_list_operator(self, autocrud_with_users):
        """Test in_list and not_in_list operators."""
        autocrud = autocrud_with_users
        user_manager: ResourceManager[User] = autocrud.resource_managers["users"]

        current_user = "test_user"
        current_time = dt.datetime.now()

        with user_manager.meta_provide(current_user, current_time):
            # Create test users
            test_users = [
                User(
                    name="Alice",
                    email="alice@test.com",
                    age=25,
                    department="Engineering",
                ),
                User(name="Bob", email="bob@test.com", age=30, department="Marketing"),
                User(
                    name="Charlie", email="charlie@test.com", age=35, department="Sales"
                ),
                User(
                    name="Diana",
                    email="diana@test.com",
                    age=28,
                    department="Engineering",
                ),
            ]

            for user_data in test_users:
                user_manager.create(user_data)

            # Test in_list operator
            query = ResourceMetaSearchQuery(
                data_conditions=[
                    DataSearchCondition(
                        field_path="department",
                        operator=DataSearchOperator.in_list,
                        value=["Engineering", "Marketing"],
                    )
                ],
            )
            results = user_manager.search_resources(query)
            assert len(results) == 3  # Alice, Bob, Diana

            # Test not_in_list operator
            query = ResourceMetaSearchQuery(
                data_conditions=[
                    DataSearchCondition(
                        field_path="department",
                        operator=DataSearchOperator.not_in_list,
                        value=["Engineering", "Marketing"],
                    )
                ],
            )
            results = user_manager.search_resources(query)
            assert len(results) == 1  # Only Charlie (Sales)

    def test_switch_revision_updates_index(self, autocrud_with_users):
        """Test that switching revisions updates the indexed data."""
        autocrud = autocrud_with_users
        user_manager: ResourceManager[User] = autocrud.resource_managers["users"]

        current_user = "test_user"
        current_time = dt.datetime.now()

        with user_manager.meta_provide(current_user, current_time):
            # Create initial user
            original_user = User(
                name="Alice",
                email="alice@company.com",
                age=25,
                department="Engineering",
            )
            create_info = user_manager.create(original_user)
            resource_id = create_info.resource_id
            original_revision_id = create_info.revision_id

            # Update user to create a new revision
            updated_user = User(
                name="Alice",
                email="alice@company.com",
                age=26,  # Changed age
                department="Marketing",  # Changed department
            )
            update_info = user_manager.update(resource_id, updated_user)
            new_revision_id = update_info.revision_id

            # Verify current state shows updated data
            current_meta = user_manager.get_meta(resource_id)
            assert current_meta.indexed_data is not UNSET
            assert current_meta.indexed_data["age"] == 26
            assert current_meta.indexed_data["department"] == "Marketing"

            # Switch back to original revision
            user_manager.switch(resource_id, original_revision_id)

            # Verify index was updated to reflect original revision data
            switched_meta = user_manager.get_meta(resource_id)
            assert switched_meta.indexed_data is not UNSET
            assert switched_meta.indexed_data["age"] == 25
            assert switched_meta.indexed_data["department"] == "Engineering"

            # Search should now find this user in Engineering department again
            query = ResourceMetaSearchQuery(
                data_conditions=[
                    DataSearchCondition(
                        field_path="department",
                        operator=DataSearchOperator.equals,
                        value="Engineering",
                    )
                ],
            )
            results = user_manager.search_resources(query)
            assert len(results) == 1
            assert results[0].resource_id == resource_id
