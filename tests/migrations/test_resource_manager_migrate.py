import datetime as dt
import io
from typing import IO
from unittest.mock import MagicMock

import msgspec
import pytest
from msgspec import Struct

from autocrud.resource_manager.core import ResourceManager
from autocrud.types import (
    IMigration,
    IndexableField,
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
            obj = msgspec.msgpack.decode(data.read(), type=LegacyData)
            return CurrentData(
                name=obj.name, _legacy_value=obj.value, new_field="migrated"
            )
        raise ValueError(f"Unsupported schema version: {schema_version}")


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
            indexed_fields=[IndexableField("name"), IndexableField("new_field")],
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

    @pytest.mark.parametrize("is_deleted", (True, False))
    def test_migrate_already_current_version(
        self,
        resource_manager: ResourceManager,
        mock_storage: MagicMock,
        *,
        is_deleted: bool,
    ) -> None:
        """測試資源已經是最新版本的情況"""
        # 設置 mock 返回值
        mock_meta = MagicMock()
        mock_meta.is_deleted = is_deleted
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

    @pytest.mark.parametrize("meta_provided", (True, False))
    @pytest.mark.parametrize("old_version", ("1.0", None))
    def test_migrate_legacy_version(
        self,
        resource_manager: ResourceManager,
        mock_storage: MagicMock,
        *,
        meta_provided: bool,
        old_version: str | None,
    ) -> None:
        """測試從舊版本遷移的情況"""
        # 創建測試數據
        legacy_revision_info = RevisionInfo(
            uid="test-uid",
            resource_id="test:123",
            revision_id="test:123:1",
            schema_version=old_version,  # 舊版本
            data_hash="old-hash",
            status=RevisionStatus.stable,
            created_time=dt.datetime.now(),
            updated_time=dt.datetime.now(),
            created_by="test_user",
            updated_by="test_user",
        )

        legacy_data = LegacyData(name="old_name", value=10)

        original_meta = ResourceMeta(
            current_revision_id="test:123:1",
            resource_id="test:123",
            schema_version=old_version,  # 舊版本
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
        mock_storage.get_data_bytes.return_value.__enter__.return_value = io.BytesIO(
            msgspec.msgpack.encode(legacy_data)
        )

        # 執行遷移
        if meta_provided:
            with resource_manager.meta_provide("admin_user", dt.datetime.now()):
                result = resource_manager.migrate("test:123")
        else:
            result = resource_manager.migrate("test:123")

        # 驗證調用
        mock_storage.exists.assert_called_once_with("test:123")
        mock_storage.get_meta.assert_called_once_with("test:123")
        mock_storage.get_resource_revision_info.assert_called_once_with(
            "test:123", original_meta.current_revision_id
        )
        mock_storage.get_data_bytes.assert_called_once_with(
            "test:123", original_meta.current_revision_id
        )

        # 驗證保存被調用
        mock_storage.save_meta.assert_called_once()
        mock_storage.save_revision.assert_called_once()

        # 檢查保存的資源
        info = mock_storage.save_revision.call_args[0][0]
        data_io = mock_storage.save_revision.call_args[0][1]
        data_io.seek(0)
        data = msgspec.json.decode(data_io.read(), type=CurrentData)
        assert info.schema_version == "2.0"  # 更新為新版本
        assert isinstance(data, CurrentData)
        assert data.name == "old_name"
        assert data._legacy_value == 10
        assert data.new_field == "migrated"

        # 檢查保存的元數據
        saved_meta = mock_storage.save_meta.call_args[0][0]
        assert result == saved_meta
        assert result.schema_version == "2.0"  # 更新為新版本
        assert result.indexed_data == {"name": "old_name", "new_field": "migrated"}
