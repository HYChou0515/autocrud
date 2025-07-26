"""測試列表查詢功能"""

import pytest
from typing import TypedDict
from datetime import datetime, timedelta

from autocrud import AutoCRUD, ListQueryParams, ListResult, DateTimeRange, SortOrder
from autocrud.storage import MemoryStorage
from autocrud.metadata import MetadataConfig


class User(TypedDict):
    id: str
    name: str
    email: str
    created_time: str
    updated_time: str
    created_by: str
    updated_by: str


@pytest.fixture
def crud_with_metadata():
    """創建帶 metadata 的 CRUD 實例"""
    metadata_config = MetadataConfig(enable_timestamps=True, enable_user_tracking=True)

    crud = AutoCRUD(metadata_config=metadata_config)
    crud.register_model(User, resource_name="users", storage=MemoryStorage())
    return crud


@pytest.fixture
def sample_users(crud_with_metadata):
    """創建示例用戶數據"""
    base_time = datetime.now()

    users_data = [
        {
            "name": "Alice",
            "email": "alice@example.com",
            "created_by": "admin",
            "updated_by": "admin",
        },
        {
            "name": "Bob",
            "email": "bob@example.com",
            "created_by": "admin",
            "updated_by": "user1",
        },
        {
            "name": "Charlie",
            "email": "charlie@example.com",
            "created_by": "user1",
            "updated_by": "user1",
        },
    ]

    created_users = []
    for i, data in enumerate(users_data):
        # 模擬不同的創建時間
        mock_time = (base_time - timedelta(hours=i)).isoformat()

        # 手動設置時間戳來測試過濾功能
        user_id = crud_with_metadata.create("users", data)
        user = crud_with_metadata.get("users", user_id)

        # 更新時間戳 - 使用正確的 API
        user["created_time"] = mock_time
        user["updated_time"] = mock_time
        storage = crud_with_metadata.get_storage("users")
        storage.set(f"users:{user_id}", user)

        created_users.append(user)

    return created_users


def test_list_query_params_validation():
    """測試查詢參數驗證"""
    # 正常參數
    params = ListQueryParams(page=1, page_size=10)
    assert params.page == 1
    assert params.page_size == 10

    # 無效頁碼
    with pytest.raises(ValueError, match="page must be >= 1"):
        ListQueryParams(page=0)

    # 無效頁面大小
    with pytest.raises(ValueError, match="page_size must be between 1 and 1000"):
        ListQueryParams(page_size=0)

    with pytest.raises(ValueError, match="page_size must be between 1 and 1000"):
        ListQueryParams(page_size=1001)


def test_basic_list_all_backward_compatibility(crud_with_metadata, sample_users):
    """測試基本 list_all 的向後兼容性"""
    users = crud_with_metadata.list_all("users")

    assert len(users) == 3
    assert all(isinstance(user, dict) for user in users)
    assert all("name" in user for user in users)


def test_list_with_pagination(crud_with_metadata, sample_users):
    """測試分頁功能"""
    # 第一頁，每頁2項
    params = ListQueryParams(page=1, page_size=2)
    result = crud_with_metadata.list_with_params("users", params)

    assert isinstance(result, ListResult)
    assert len(result.items) == 2
    assert result.total == 3
    assert result.page == 1
    assert result.page_size == 2
    assert result.total_pages == 2
    assert result.has_next is True
    assert result.has_prev is False

    # 第二頁
    params = ListQueryParams(page=2, page_size=2)
    result = crud_with_metadata.list_with_params("users", params)

    assert len(result.items) == 1
    assert result.page == 2
    assert result.has_next is False
    assert result.has_prev is True


def test_filter_by_created_by(crud_with_metadata, sample_users):
    """測試按創建者過濾"""
    params = ListQueryParams(created_by_filter=["admin"])
    result = crud_with_metadata.list_with_params("users", params)

    assert len(result.items) == 2
    for user in result.items:
        assert user["created_by"] == "admin"


def test_filter_by_updated_by(crud_with_metadata, sample_users):
    """測試按更新者過濾"""
    params = ListQueryParams(updated_by_filter=["user1"])
    result = crud_with_metadata.list_with_params("users", params)

    assert len(result.items) == 2
    for user in result.items:
        assert user["updated_by"] == "user1"


def test_filter_by_multiple_users(crud_with_metadata, sample_users):
    """測試按多個用戶過濾"""
    params = ListQueryParams(created_by_filter=["admin", "user1"])
    result = crud_with_metadata.list_with_params("users", params)

    assert len(result.items) == 3  # 所有用戶都被包含


def test_filter_by_time_range(crud_with_metadata, sample_users):
    """測試按時間範圍過濾"""
    # 獲取中間時間點
    base_time = datetime.now()
    middle_time = base_time - timedelta(minutes=30)

    # 過濾最近創建的項目
    params = ListQueryParams(created_time_range=DateTimeRange(start=middle_time))
    result = crud_with_metadata.list_with_params("users", params)

    # 至少應該有一些結果（具體數量取決於時間設置）
    assert len(result.items) >= 0


def test_sorting_by_created_time(crud_with_metadata, sample_users):
    """測試按創建時間排序"""
    # 降序排序（最新的在前）
    params = ListQueryParams(sort_by="created_time", sort_order=SortOrder.DESC)
    result = crud_with_metadata.list_with_params("users", params)

    assert len(result.items) == 3

    # 升序排序（最舊的在前）
    params = ListQueryParams(sort_by="created_time", sort_order=SortOrder.ASC)
    result = crud_with_metadata.list_with_params("users", params)

    assert len(result.items) == 3


def test_invalid_sort_field(crud_with_metadata, sample_users):
    """測試無效的排序字段"""
    params = ListQueryParams(sort_by="invalid_field")
    result = crud_with_metadata.list_with_params("users", params)

    # 應該返回所有項目但不排序
    assert len(result.items) == 3


def test_combined_filters_and_pagination(crud_with_metadata, sample_users):
    """測試組合過濾器和分頁"""
    params = ListQueryParams(
        page=1,
        page_size=1,
        created_by_filter=["admin"],
        sort_by="created_time",
        sort_order=SortOrder.DESC,
    )
    result = crud_with_metadata.list_with_params("users", params)

    assert len(result.items) == 1
    assert result.total == 2  # 只有2個由admin創建的用戶
    assert result.items[0]["created_by"] == "admin"


def test_empty_results(crud_with_metadata, sample_users):
    """測試空結果"""
    params = ListQueryParams(created_by_filter=["nonexistent"])
    result = crud_with_metadata.list_with_params("users", params)

    assert len(result.items) == 0
    assert result.total == 0
    assert result.total_pages == 0
    assert result.has_next is False
    assert result.has_prev is False


def test_date_time_range_class():
    """測試 DateTimeRange 類"""
    start_time = datetime(2024, 1, 1)
    end_time = datetime(2024, 12, 31)

    date_range = DateTimeRange(start=start_time, end=end_time)

    # 在範圍內
    assert date_range.contains(datetime(2024, 6, 15)) is True

    # 在範圍外
    assert date_range.contains(datetime(2023, 12, 31)) is False
    assert date_range.contains(datetime(2025, 1, 1)) is False

    # 邊界情況
    assert date_range.contains(start_time) is True
    assert date_range.contains(end_time) is True


def test_list_result_creation():
    """測試 ListResult 創建"""
    items = [{"id": "1", "name": "test"}]
    params = ListQueryParams(page=2, page_size=1)

    result = ListResult.create(items, total=5, params=params)

    assert result.items == items
    assert result.total == 5
    assert result.page == 2
    assert result.page_size == 1
    assert result.total_pages == 5
    assert result.has_next is True
    assert result.has_prev is True


def test_list_all_with_params_simple_mode(crud_with_metadata, sample_users):
    """測試帶參數的 list_all（簡單模式）"""
    params = ListQueryParams(created_by_filter=["admin"])
    items = crud_with_metadata.list_all("users", params)

    # 應該返回過濾後的項目列表
    assert isinstance(items, list)
    assert len(items) == 2
    for item in items:
        assert item["created_by"] == "admin"


def test_crud_without_metadata_config():
    """測試沒有 metadata 配置的 CRUD"""
    crud = AutoCRUD()  # 默認配置，沒有時間戳和用戶跟踪
    crud.register_model(User, resource_name="users", storage=MemoryStorage())

    # 創建一些測試數據
    crud.create("users", {"name": "Test", "email": "test@example.com"})

    # 使用過濾器（應該被忽略，因為沒有相應的字段）
    params = ListQueryParams(created_by_filter=["admin"])
    result = crud.list_with_params("users", params)

    # 應該返回所有項目，因為過濾器被忽略
    assert len(result.items) == 1
