"""測試 S3StorageFactory"""

import datetime as dt
from enum import Enum

import pytest
from msgspec import Struct

from autocrud import AutoCRUD
from autocrud.query import QB
from autocrud.resource_manager.s3_storage_factory import S3StorageFactory
from autocrud.types import Binary


class CategoryEnum(Enum):
    OPTION_A = "A"
    OPTION_B = "B"
    OPTION_C = "C"


class SampleModel(Struct):
    name: str
    value: int
    category: CategoryEnum
    tags: list[str] = []
    avatar: Binary | None = None


@pytest.fixture
def s3_storage_factory(request):
    """建立 S3StorageFactory (使用 MinIO)，每個測試使用獨立 prefix"""
    # 使用測試名稱作為 prefix 避免衝突
    test_name = request.node.name
    return S3StorageFactory(
        bucket="test-autocrud",
        endpoint_url="http://localhost:9000",
        access_key_id="minioadmin",
        secret_access_key="minioadmin",
        prefix=f"test/{test_name}/",
        auto_sync=True,
        sync_interval=0,  # 立即同步
    )


@pytest.fixture
def crud_with_s3(s3_storage_factory):
    """建立使用 S3 backend 的 AutoCRUD"""
    crud = AutoCRUD(storage_factory=s3_storage_factory)
    crud.add_model(
        SampleModel,
        indexed_fields=[
            ("name", str),
            ("value", int),
            ("category", CategoryEnum),
        ],
    )
    return crud


def test_s3_storage_factory_basic(crud_with_s3):
    """測試 S3StorageFactory 基本功能"""
    manager = crud_with_s3.get_resource_manager(SampleModel)
    assert manager is not None

    # 建立測試數據
    with manager.meta_provide("test_user", dt.datetime.now()):
        data = SampleModel(
            name="Test Item",
            value=100,
            category=CategoryEnum.OPTION_A,
            tags=["tag1", "tag2"],
        )
        info = manager.create(data)

    # 驗證數據已儲存
    resource = manager.get(info.resource_id)
    assert resource.data.name == "Test Item"
    assert resource.data.value == 100
    assert resource.data.category == CategoryEnum.OPTION_A
    assert resource.data.tags == ["tag1", "tag2"]


@pytest.mark.skip(reason="需要 MinIO 服務進行實際的 S3 操作")
def test_s3_storage_factory_search(crud_with_s3):
    """測試 S3StorageFactory 搜尋功能"""
    manager = crud_with_s3.get_resource_manager(SampleModel)

    # 建立多筆測試數據
    with manager.meta_provide("test_user", dt.datetime.now()):
        for i in range(5):
            data = SampleModel(
                name=f"Item {i}",
                value=i * 10,
                category=CategoryEnum.OPTION_A if i % 2 == 0 else CategoryEnum.OPTION_B,
            )
            manager.create(data)

    # 使用 QueryBuilder 搜尋
    query = QB["value"].gte(20).sort("-value").limit(3)
    metas = manager.search_resources(query)

    assert len(metas) == 3
    resources = [manager.get(meta.resource_id) for meta in metas]
    assert resources[0].data.value == 40
    assert resources[1].data.value == 30
    assert resources[2].data.value == 20


def test_s3_storage_factory_versioning(crud_with_s3):
    """測試 S3StorageFactory 資料更新"""
    manager = crud_with_s3.get_resource_manager(SampleModel)

    # 建立初始版本
    with manager.meta_provide("test_user", dt.datetime.now()):
        data = SampleModel(name="Original", value=100, category=CategoryEnum.OPTION_A)
        info = manager.create(data)

    # 更新資料
    with manager.meta_provide("test_user", dt.datetime.now()):
        modified_data = SampleModel(
            name="Modified", value=200, category=CategoryEnum.OPTION_B
        )
        manager.update(info.resource_id, modified_data)

    # 驗證新版本
    resource = manager.get(info.resource_id)
    assert resource.data.name == "Modified"
    assert resource.data.value == 200
    assert resource.data.category == CategoryEnum.OPTION_B


@pytest.mark.skip(reason="需要 MinIO 服務和完整的 blob store 支持")
def test_s3_storage_factory_blob(crud_with_s3):
    """測試 S3StorageFactory 二進制數據存儲"""
    manager = crud_with_s3.get_resource_manager(SampleModel)

    # 建立包含二進制數據的資源
    test_image = b"fake image data" * 100
    with manager.meta_provide("test_user", dt.datetime.now()):
        data = SampleModel(
            name="With Image",
            value=100,
            category=CategoryEnum.OPTION_A,
            avatar=Binary(data=test_image),
        )
        info = manager.create(data)

    # 驗證二進制數據
    resource = manager.get(info.resource_id)
    assert resource.data.avatar is not None
    assert resource.data.avatar.size == len(test_image)
    assert resource.data.avatar.data == test_image
    assert resource.data.avatar.file_id is not None  # 應該有 file_id


def test_s3_storage_factory_delete_and_list(crud_with_s3):
    """測試 S3StorageFactory 刪除和列表功能"""
    manager = crud_with_s3.get_resource_manager(SampleModel)

    # 建立測試數據
    with manager.meta_provide("test_user", dt.datetime.now()):
        info1 = manager.create(
            SampleModel(name="Item 1", value=100, category=CategoryEnum.OPTION_A)
        )
        info2 = manager.create(
            SampleModel(name="Item 2", value=200, category=CategoryEnum.OPTION_B)
        )

    # 驗證可以列出所有資源
    all_metas = manager.search_resources(QB["value"].gte(0).limit(100))
    assert len(all_metas) >= 2

    # 刪除一個資源
    with manager.meta_provide("test_user", dt.datetime.now()):
        manager.delete(info1.resource_id)

    # 驗證已刪除 - 使用 search 查詢已刪除的資源
    from autocrud.types import ResourceMetaSearchQuery

    deleted_query = ResourceMetaSearchQuery(is_deleted=True, limit=100)
    deleted_metas = manager.search_resources(deleted_query)
    deleted_ids = [m.resource_id for m in deleted_metas]
    assert info1.resource_id in deleted_ids


def test_s3_storage_factory_enum_search(crud_with_s3):
    """測試 S3StorageFactory Enum 欄位搜尋"""
    manager = crud_with_s3.get_resource_manager(SampleModel)

    # 建立不同 category 的數據
    with manager.meta_provide("test_user", dt.datetime.now()):
        manager.create(SampleModel(name="A1", value=1, category=CategoryEnum.OPTION_A))
        manager.create(SampleModel(name="A2", value=2, category=CategoryEnum.OPTION_A))
        manager.create(SampleModel(name="B1", value=3, category=CategoryEnum.OPTION_B))
        manager.create(SampleModel(name="C1", value=4, category=CategoryEnum.OPTION_C))

    # 搜尋特定 category (Enum 已被轉換為值)
    query = QB["category"].eq("A").limit(10)
    metas = manager.search_resources(query)
    assert len(metas) >= 2

    resources = [manager.get(meta.resource_id) for meta in metas]
    for resource in resources:
        assert resource.data.category == CategoryEnum.OPTION_A


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
