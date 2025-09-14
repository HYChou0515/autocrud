import datetime as dt
from typing import IO
from unittest.mock import MagicMock

import pytest
from msgspec import UNSET, Struct

from autocrud.resource_manager.core import ResourceManager
from autocrud.types import (
    IMigration,
    Resource,
    ResourceMeta,
    RevisionInfo,
    RevisionStatus,
)


# 測試用的數據結構
class LegacyData(Struct):
    name: str
    value: int


class CurrentData(Struct):
    name: str
    _legacy_value: int
    new_field: str


# 測試用的遷移實現
class MigrationImpl(IMigration[CurrentData]):
    def __init__(self, target_schema_version: str = "2.0"):
        self._schema_version = target_schema_version

    @property
    def schema_version(self) -> str:
        return self._schema_version

    def migrate(self, data: IO[bytes], schema_version: str | None) -> CurrentData:
        """遷移數據"""
        if schema_version == "1.0" or schema_version is None:
            # 模擬從舊版本遷移
            return CurrentData(name="migrated_name", value=42, new_field="migrated")
        return CurrentData(name="current_name", value=100, new_field="current")

    def migrate_meta(
        self,
        meta: ResourceMeta,
        resource: Resource[CurrentData],
        schema_version: str | None,
    ) -> ResourceMeta:
        """遷移元數據"""
        if schema_version == "1.0" or schema_version is None:
            meta.schema_version = self._schema_version
            meta.indexed_data = {
                "name": resource.data.name,
                "value": resource.data.value,
                "new_field": resource.data.new_field,
            }
        return meta


class TestResourceManagerMigrate:
    """測試 ResourceManager 的 migrate 方法"""

    @pytest.fixture
    def mock_storage(self) -> MagicMock:
        """創建模擬的 storage"""
        storage = MagicMock()
        return storage

    @pytest.fixture
    def test_migration(self) -> MigrationImpl:
        """創建測試用的遷移器"""
        return MigrationImpl()

    @pytest.fixture
    def resource_manager(
        self, mock_storage: MagicMock, test_migration: MigrationImpl
    ) -> ResourceManager:
        """創建包含遷移器的 ResourceManager"""
        return ResourceManager(
            resource_type=CurrentData,
            storage=mock_storage,
            migration=test_migration,
        )

    @pytest.fixture
    def resource_manager_no_migration(self, mock_storage: MagicMock) -> ResourceManager:
        """創建沒有遷移器的 ResourceManager"""
        return ResourceManager(
            resource_type=CurrentData,
            storage=mock_storage,
        )

    def test_migrate_no_migration_set(
        self, resource_manager_no_migration: ResourceManager
    ) -> None:
        """測試沒有設置遷移器時的錯誤"""
        with pytest.raises(
            ValueError, match="Migration is not set for this resource manager"
        ):
            resource_manager_no_migration.migrate("test:123")

    def test_migrate_already_current_version(
        self, resource_manager: ResourceManager, mock_storage: MagicMock
    ) -> None:
        """測試資源已經是最新版本的情況"""
        # 設置 mock 返回值
        mock_meta = MagicMock()
        mock_meta.is_deleted = False  # 確保資源沒有被刪除
        mock_info = MagicMock()
        mock_info.schema_version = "2.0"  # 已經是最新版本

        # MagicMock storage methods properly
        mock_storage.exists.return_value = True
        mock_storage.get_meta.return_value = mock_meta
        mock_storage.get_resource_revision_info.return_value = mock_info
        # 執行遷移
        result = resource_manager.migrate("test:123")

        # 驗證結果
        assert result == mock_meta

        # 驗證調用 - migrate 方法內部調用 get_meta 和 get 方法
        mock_storage.exists.assert_called_with("test:123")
        mock_storage.get_meta.assert_called_with("test:123")
        mock_storage.get_resource_revision_info.assert_called_with(
            "test:123", mock_meta.current_revision_id
        )

    def test_migrate_legacy_version(
        self,
        resource_manager: ResourceManager,
        mock_storage: MagicMock,
        test_migration: MigrationImpl,
    ) -> None:
        """測試從舊版本遷移的情況"""
        # 創建測試數據
        legacy_revision_info = RevisionInfo(
            uid="test-uid",
            resource_id="test:123",
            revision_id="test:123:1",
            schema_version="1.0",  # 舊版本
            data_hash="old-hash",
            status=RevisionStatus.stable,
            created_time=dt.datetime.now(),
            updated_time=dt.datetime.now(),
            created_by="test_user",
            updated_by="test_user",
        )

        legacy_data = LegacyData(name="old_name", value=10)
        legacy_resource = Resource(info=legacy_revision_info, data=legacy_data)

        original_meta = ResourceMeta(
            current_revision_id="test:123:1",
            resource_id="test:123",
            schema_version="1.0",  # 舊版本
            total_revision_count=1,
            created_time=dt.datetime.now(),
            updated_time=dt.datetime.now(),
            created_by="test_user",
            updated_by="test_user",
        )
        original_meta.is_deleted = False  # 確保資源沒有被刪除

        # 設置 mock 返回值
        mock_storage.exists.return_value = True
        mock_storage.get_meta.return_value = original_meta
        mock_storage.get_resource_revision_info.return_value = legacy_revision_info

        # 執行遷移
        result = resource_manager.migrate("test:123")

        # 驗證調用
        mock_storage.get_resource_revision.assert_called_once()
        assert mock_storage.get_meta.call_count == 2  # 被 get() 和 migrate() 各調用一次
        mock_storage.encode_data.assert_called_once_with(legacy_data)

        # 驗證保存被調用
        assert mock_storage.save_resource_revision.called
        assert mock_storage.save_meta.called

        # 檢查保存的資源
        saved_resource = mock_storage.save_resource_revision.call_args[0][0]
        assert saved_resource.info.schema_version == "2.0"  # 更新為新版本
        assert isinstance(saved_resource.data, CurrentData)
        assert saved_resource.data.name == "migrated_name"
        assert saved_resource.data.value == 42
        assert saved_resource.data.new_field == "migrated"

        # 檢查保存的元數據
        saved_meta = mock_storage.save_meta.call_args[0][0]
        assert saved_meta.schema_version == "2.0"  # 更新為新版本
        assert "name" in saved_meta.indexed_data
        assert "value" in saved_meta.indexed_data
        assert "new_field" in saved_meta.indexed_data

    def test_migrate_with_context(
        self, resource_manager: ResourceManager, mock_storage: MagicMock
    ) -> None:
        """測試帶有用戶上下文的遷移"""
        # 創建測試數據
        legacy_revision_info = RevisionInfo(
            uid="test-uid",
            resource_id="test:123",
            revision_id="test:123:1",
            schema_version="1.0",
            data_hash="old-hash",
            status=RevisionStatus.stable,
            created_time=dt.datetime.now(),
            updated_time=dt.datetime.now(),
            created_by="original_user",
            updated_by="original_user",
        )

        legacy_data = LegacyData(name="old_name", value=10)
        legacy_resource = Resource(info=legacy_revision_info, data=legacy_data)

        original_meta = ResourceMeta(
            current_revision_id="test:123:1",
            resource_id="test:123",
            schema_version="1.0",
            total_revision_count=1,
            created_time=dt.datetime.now(),
            updated_time=dt.datetime.now(),
            created_by="original_user",
            updated_by="original_user",
        )
        original_meta.is_deleted = False

        # 設置 mock 返回值
        mock_storage.exists.return_value = True
        mock_storage.get_meta.return_value = original_meta
        mock_storage.get_resource_revision.return_value = legacy_resource
        mock_storage.encode_data.return_value = b'{"name": "old_name", "value": 10}'

        # 設置用戶上下文
        test_user = "migration_user"
        test_time = dt.datetime.now()

        with resource_manager.meta_provide(test_user, test_time):
            result = resource_manager.migrate("test:123")

        # 驗證遷移執行正確
        assert mock_storage.save_resource_revision.called
        assert mock_storage.save_meta.called

    def test_migrate_unset_schema_version(
        self, resource_manager: ResourceManager, mock_storage: MagicMock
    ) -> None:
        """測試 schema_version 為 UNSET 的情況"""
        # 創建測試數據
        legacy_revision_info = RevisionInfo(
            uid="test-uid",
            resource_id="test:123",
            revision_id="test:123:1",
            schema_version=UNSET,  # UNSET 版本
            data_hash="old-hash",
            status=RevisionStatus.stable,
            created_time=dt.datetime.now(),
            updated_time=dt.datetime.now(),
            created_by="test_user",
            updated_by="test_user",
        )

        legacy_data = LegacyData(name="old_name", value=10)
        legacy_resource = Resource(info=legacy_revision_info, data=legacy_data)

        original_meta = ResourceMeta(
            current_revision_id="test:123:1",
            resource_id="test:123",
            schema_version=UNSET,  # UNSET 版本
            total_revision_count=1,
            created_time=dt.datetime.now(),
            updated_time=dt.datetime.now(),
            created_by="test_user",
            updated_by="test_user",
        )
        original_meta.is_deleted = False

        # 設置 mock 返回值
        mock_storage.exists.return_value = True
        mock_storage.get_meta.return_value = original_meta
        mock_storage.get_resource_revision.return_value = legacy_resource
        mock_storage.encode_data.return_value = b'{"name": "old_name", "value": 10}'

        # 執行遷移
        result = resource_manager.migrate("test:123")

        # 驗證遷移被執行（UNSET 被視為需要遷移）
        assert mock_storage.save_resource_revision.called
        assert mock_storage.save_meta.called

        # 檢查保存的資源版本被更新
        saved_resource = mock_storage.save_resource_revision.call_args[0][0]
        assert saved_resource.info.schema_version == "2.0"

    def test_migrate_custom_migration_logic(self, mock_storage: MagicMock) -> None:
        """測試自定義遷移邏輯"""

        # 創建一個特殊的遷移器，用於測試自定義邏輯
        class CustomMigration(IMigration[CurrentData]):
            @property
            def schema_version(self) -> str:
                return "3.0"

            def migrate(
                self, data: IO[bytes], schema_version: str | None
            ) -> CurrentData:
                return CurrentData(
                    name="custom_migrated", value=999, new_field="custom_field"
                )

            def migrate_meta(
                self,
                meta: ResourceMeta,
                resource: Resource[CurrentData],
                schema_version: str | None,
            ) -> ResourceMeta:
                meta.schema_version = self.schema_version
                meta.indexed_data = {"custom": "migration"}
                return meta

        custom_migration = CustomMigration()
        resource_manager = ResourceManager(
            resource_type=CurrentData,
            storage=mock_storage,
            migration=custom_migration,
        )

        # 創建測試數據
        legacy_revision_info = RevisionInfo(
            uid="test-uid",
            resource_id="test:123",
            revision_id="test:123:1",
            schema_version="1.0",
            data_hash="old-hash",
            status=RevisionStatus.stable,
            created_time=dt.datetime.now(),
            updated_time=dt.datetime.now(),
            created_by="test_user",
            updated_by="test_user",
        )

        legacy_data = LegacyData(name="old_name", value=10)
        legacy_resource = Resource(info=legacy_revision_info, data=legacy_data)

        original_meta = ResourceMeta(
            current_revision_id="test:123:1",
            resource_id="test:123",
            schema_version="1.0",
            total_revision_count=1,
            created_time=dt.datetime.now(),
            updated_time=dt.datetime.now(),
            created_by="test_user",
            updated_by="test_user",
        )
        original_meta.is_deleted = False

        # 設置 mock 返回值
        mock_storage.exists.return_value = True
        mock_storage.get_meta.return_value = original_meta
        mock_storage.get_resource_revision.return_value = legacy_resource
        mock_storage.encode_data.return_value = b'{"name": "old_name", "value": 10}'

        # 執行遷移
        result = resource_manager.migrate("test:123")

        # 驗證自定義遷移被正確執行
        saved_resource = mock_storage.save_resource_revision.call_args[0][0]
        assert saved_resource.info.schema_version == "3.0"
        assert saved_resource.data.name == "custom_migrated"
        assert saved_resource.data.value == 999
        assert saved_resource.data.new_field == "custom_field"

        saved_meta = mock_storage.save_meta.call_args[0][0]
        assert saved_meta.schema_version == "3.0"
        assert saved_meta.indexed_data == {"custom": "migration"}
