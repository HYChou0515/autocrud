"""測試 migrate route template 功能"""

import datetime as dt
import json
from typing import Any, AsyncGenerator, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import msgspec
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from autocrud.crud.route_templates.migrate import (
    MigrateProgress,
    MigrateResult,
    MigrateRouteTemplate,
)
from autocrud.types import (
    DataSearchCondition,
    DataSearchOperator,
    ResourceMetaSearchQuery,
)


class User(msgspec.Struct):
    name: str
    email: str
    age: int


class UserV2(msgspec.Struct):
    """用於測試 schema migration 的 User V2"""

    name: str
    email: str
    age: int
    department: str = "Unknown"  # 新增欄位


class MockMigration:
    """Mock Migration 類別用於測試"""

    @property
    def schema_version(self) -> str:
        return "2.0"

    def migrate(self, data: User, schema_version: str) -> UserV2:
        # 模擬遷移邏輯
        if schema_version == "1.0":
            return UserV2(
                name=data.name, email=data.email, age=data.age, department="Migrated"
            )
        return data


@pytest.fixture
def mock_resource_manager() -> Mock:
    """創建 mock resource manager"""
    manager = Mock()
    manager.schema_version = "2.0"
    manager.resource_type = User

    # Mock meta_provide context manager
    context_manager = Mock()
    context_manager.__enter__ = Mock(return_value=None)
    context_manager.__exit__ = Mock(return_value=None)
    manager.meta_provide.return_value = context_manager

    return manager


@pytest.fixture
def migrate_template() -> MigrateRouteTemplate:
    """創建 migrate route template"""
    return MigrateRouteTemplate()


@pytest.fixture
def app_with_migrate_routes(
    migrate_template: MigrateRouteTemplate, mock_resource_manager: Mock
) -> FastAPI:
    """創建包含 migrate routes 的 FastAPI app"""
    app = FastAPI()
    router = APIRouter()

    # 應用 migrate routes
    migrate_template.apply("user", mock_resource_manager, router)
    app.include_router(router)

    return app


@pytest.fixture
def client(app_with_migrate_routes: FastAPI) -> TestClient:
    """創建測試客戶端"""
    return TestClient(app_with_migrate_routes)


class TestMigrateProgress:
    """測試 MigrateProgress 資料結構"""

    def test_migrate_progress_success(self) -> None:
        """測試成功的遷移進度"""
        progress = MigrateProgress(
            resource_id="user:123",
            status="success",
            message="Migration completed successfully",
        )

        assert progress.resource_id == "user:123"
        assert progress.status == "success"
        assert progress.message == "Migration completed successfully"
        assert progress.error is None

    def test_migrate_progress_failed(self) -> None:
        """測試失敗的遷移進度"""
        progress = MigrateProgress(
            resource_id="user:456", status="failed", error="Schema version mismatch"
        )

        assert progress.resource_id == "user:456"
        assert progress.status == "failed"
        assert progress.error == "Schema version mismatch"
        assert progress.message is None

    def test_migrate_progress_skipped(self) -> None:
        """測試跳過的遷移進度"""
        progress = MigrateProgress(
            resource_id="user:789",
            status="skipped",
            message="Already at current schema version",
        )

        assert progress.resource_id == "user:789"
        assert progress.status == "skipped"
        assert progress.message == "Already at current schema version"


class TestMigrateResult:
    """測試 MigrateResult 資料結構"""

    def test_migrate_result_basic(self) -> None:
        """測試基本的遷移結果"""
        result = MigrateResult(total=10, success=8, failed=1, skipped=1)

        assert result.total == 10
        assert result.success == 8
        assert result.failed == 1
        assert result.skipped == 1
        assert result.errors == []

    def test_migrate_result_with_errors(self) -> None:
        """測試包含錯誤的遷移結果"""
        errors: List[Dict[str, str]] = [
            {"resource_id": "user:123", "error": "Migration failed"},
            {"resource_id": "user:456", "error": "Schema error"},
        ]

        result = MigrateResult(total=5, success=3, failed=2, skipped=0, errors=errors)

        assert result.total == 5
        assert result.success == 3
        assert result.failed == 2
        assert result.skipped == 0
        assert len(result.errors) == 2
        assert result.errors[0]["resource_id"] == "user:123"


class TestMigrateSingleResource:
    """測試單一資源遷移功能"""

    @pytest.mark.asyncio
    async def test_migrate_single_resource_success(
        self, migrate_template: MigrateRouteTemplate, mock_resource_manager: Mock
    ) -> None:
        """測試成功遷移單一資源"""
        # 設置 mock 資料
        mock_meta = Mock()
        mock_resource = Mock()
        mock_resource.info.schema_version = "1.0"
        mock_migrated_resource = Mock()
        mock_migrated_resource.resource_id = "user:123"

        mock_resource_manager.get_meta.return_value = mock_meta
        mock_resource_manager.get.return_value = mock_resource
        mock_resource_manager.migrate.return_value = mock_migrated_resource

        # 執行遷移
        progress = await migrate_template._migrate_single_resource(
            mock_resource_manager,
            "user:123",
            "test_user",
            dt.datetime.now(),
            write_back=True,
        )

        assert progress.resource_id == "user:123"
        assert progress.status == "success"
        assert "Migrated user:123 from" in progress.message
        assert progress.error is None

    @pytest.mark.asyncio
    async def test_migrate_single_resource_skipped(
        self, migrate_template: MigrateRouteTemplate, mock_resource_manager: Mock
    ) -> None:
        """測試跳過不需要遷移的資源"""
        # 設置 mock 資料 - 已經是最新版本
        mock_meta = Mock()
        mock_meta.schema_version = "2.0"  # 已經是最新版本
        mock_resource = Mock()

        mock_resource_manager.get_meta.return_value = mock_meta
        mock_resource_manager.get.return_value = mock_resource

        # 執行遷移
        progress = await migrate_template._migrate_single_resource(
            mock_resource_manager,
            "user:123",
            "test_user",
            dt.datetime.now(),
            write_back=True,
        )

        assert progress.resource_id == "user:123"
        assert progress.status == "skipped"
        assert "Resource already at current schema version" in progress.message
        assert progress.error is None

    @pytest.mark.asyncio
    async def test_migrate_single_resource_memory_only(
        self, migrate_template: MigrateRouteTemplate, mock_resource_manager: Mock
    ) -> None:
        """測試僅在記憶體中測試遷移"""
        # 設置 mock 資料
        mock_meta = Mock()
        mock_resource = Mock()
        mock_resource.info.schema_version = "1.0"

        mock_resource_manager.get_meta.return_value = mock_meta
        mock_resource_manager.get.return_value = mock_resource

        # 執行記憶體測試遷移
        progress = await migrate_template._migrate_single_resource(
            mock_resource_manager,
            "user:123",
            "test_user",
            dt.datetime.now(),
            write_back=False,  # 只在記憶體中測試
        )

        assert progress.resource_id == "user:123"
        assert progress.status == "success"
        assert progress.message == "Migration simulation successful"
        assert progress.error is None

        # 確認沒有調用 migrate 方法
        mock_resource_manager.migrate.assert_not_called()

    @pytest.mark.asyncio
    async def test_migrate_single_resource_failed(
        self, migrate_template: MigrateRouteTemplate, mock_resource_manager: Mock
    ) -> None:
        """測試遷移失敗的情況"""
        # 設置 mock 讓遷移拋出異常
        mock_resource_manager.get_meta.side_effect = Exception("Resource not found")

        # 執行遷移
        progress = await migrate_template._migrate_single_resource(
            mock_resource_manager,
            "user:123",
            "test_user",
            dt.datetime.now(),
            write_back=True,
        )

        assert progress.resource_id == "user:123"
        assert progress.status == "failed"
        assert "Resource not found" in progress.error
        assert progress.message is None


class TestMigrateResourcesGenerator:
    """測試批次遷移生成器功能"""

    @pytest.mark.asyncio
    async def test_migrate_resources_generator_with_query(
        self, migrate_template: MigrateRouteTemplate, mock_resource_manager: Mock
    ) -> None:
        """測試使用查詢條件的批次遷移"""
        # 設置 mock search results
        mock_metas = [Mock(resource_id="user:1"), Mock(resource_id="user:2")]
        mock_resource_manager.search_resources.return_value = mock_metas

        # Mock _migrate_single_resource
        async def mock_migrate_single(
            manager: Mock,
            resource_id: str,
            user: str,
            time: dt.datetime,
            write_back: bool,
        ) -> MigrateProgress:
            return MigrateProgress(
                resource_id=resource_id,
                status="success",
                message="Migrated successfully",
            )

        migrate_template._migrate_single_resource = mock_migrate_single

        # 創建查詢條件
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

        # 執行批次遷移
        results: List[MigrateProgress] = []
        async for progress in migrate_template._migrate_resources_generator(
            mock_resource_manager,
            query,
            "test_user",
            dt.datetime.now(),
            write_back=True,
        ):
            results.append(progress)

        assert len(results) == 2
        assert all(result.status == "success" for result in results)
        mock_resource_manager.search_resources.assert_called_once_with(query)

    @pytest.mark.asyncio
    async def test_migrate_resources_generator_no_query(
        self, migrate_template: MigrateRouteTemplate, mock_resource_manager: Mock
    ) -> None:
        """測試不使用查詢條件的批次遷移（所有資源）"""
        # 設置 mock search results for all resources
        mock_metas = [
            Mock(resource_id="user:1"),
            Mock(resource_id="user:2"),
            Mock(resource_id="user:3"),
        ]
        mock_resource_manager.search_resources.return_value = mock_metas

        # Mock _migrate_single_resource
        async def mock_migrate_single(
            manager: Mock,
            resource_id: str,
            user: str,
            time: dt.datetime,
            write_back: bool,
        ) -> MigrateProgress:
            return MigrateProgress(
                resource_id=resource_id,
                status="success",
                message="Migrated successfully",
            )

        migrate_template._migrate_single_resource = mock_migrate_single

        # 執行批次遷移（無查詢條件）
        results: List[MigrateProgress] = []
        async for progress in migrate_template._migrate_resources_generator(
            mock_resource_manager,
            None,  # 沒有查詢條件
            "test_user",
            dt.datetime.now(),
            write_back=True,
        ):
            results.append(progress)

        assert len(results) == 3
        # 確認調用了 search_resources 並傳入空的 ResourceMetaSearchQuery
        mock_resource_manager.search_resources.assert_called_once()
        call_args = mock_resource_manager.search_resources.call_args[0][0]
        assert isinstance(call_args, ResourceMetaSearchQuery)

    @pytest.mark.asyncio
    async def test_migrate_resources_generator_error(
        self, migrate_template: MigrateRouteTemplate, mock_resource_manager: Mock
    ) -> None:
        """測試批次遷移過程中發生錯誤"""
        # 設置 mock 讓 search_resources 拋出異常
        mock_resource_manager.search_resources.side_effect = Exception("Database error")

        # 執行批次遷移
        results: List[MigrateProgress] = []
        async for progress in migrate_template._migrate_resources_generator(
            mock_resource_manager, None, "test_user", dt.datetime.now(), write_back=True
        ):
            results.append(progress)

        assert len(results) == 1
        assert results[0].status == "failed"
        assert "Migration process failed: Database error" in results[0].error


class TestMigrateSingleResourceAPI:
    """測試單一資源遷移 API"""

    def test_migrate_single_resource_success(
        self, client: TestClient, mock_resource_manager: Mock
    ) -> None:
        """測試成功遷移單一資源的 API"""
        # 設置 mock 返回成功的進度
        with patch.object(
            MigrateRouteTemplate, "_migrate_single_resource", new_callable=AsyncMock
        ) as mock_migrate:
            mock_migrate.return_value = MigrateProgress(
                resource_id="user:123", status="success", message="Migration completed"
            )

            response = client.post("/user/migrate/single/user:123")

            assert response.status_code == 200
            data = response.json()
            assert data["resource_id"] == "user:123"
            assert data["status"] == "success"
            assert data["message"] == "Migration completed"

    def test_migrate_single_resource_with_write_back_false(
        self, client: TestClient, mock_resource_manager: Mock
    ) -> None:
        """測試不寫回 storage 的單一資源遷移"""
        with patch.object(
            MigrateRouteTemplate, "_migrate_single_resource", new_callable=AsyncMock
        ) as mock_migrate:
            mock_migrate.return_value = MigrateProgress(
                resource_id="user:123",
                status="success",
                message="Migration test successful",
            )

            response = client.post("/user/migrate/single/user:123?write_back=false")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"

            # 確認調用時 write_back=False
            mock_migrate.assert_called_once()
            # 檢查 keyword arguments
            call_kwargs = mock_migrate.call_args.kwargs
            assert call_kwargs["write_back"] is False

    def test_migrate_single_resource_failed(
        self, client: TestClient, mock_resource_manager: Mock
    ) -> None:
        """測試單一資源遷移失敗"""
        with patch.object(
            MigrateRouteTemplate, "_migrate_single_resource", new_callable=AsyncMock
        ) as mock_migrate:
            mock_migrate.return_value = MigrateProgress(
                resource_id="user:123", status="failed", error="Migration error"
            )

            response = client.post("/user/migrate/single/user:123")

            assert response.status_code == 400
            assert "Migration error" in response.json()["detail"]

    def test_migrate_single_resource_not_found(
        self, client: TestClient, mock_resource_manager: Mock
    ) -> None:
        """測試不存在的資源遷移"""
        with patch.object(
            MigrateRouteTemplate, "_migrate_single_resource", new_callable=AsyncMock
        ) as mock_migrate:
            mock_migrate.side_effect = Exception("Resource not found")

            response = client.post("/user/migrate/single/nonexistent")

            assert response.status_code == 404
            assert "Resource not found" in response.json()["detail"]


class TestWebSocketMigration:
    """測試 WebSocket 遷移功能"""

    def test_websocket_test_migration_success(self, client: TestClient) -> None:
        """測試 WebSocket 測試遷移成功"""

        # Mock the generator to return test results
        async def mock_generator(
            manager: Mock, query: Any, user: str, time: dt.datetime, write_back: bool
        ) -> AsyncGenerator[MigrateProgress, None]:
            # 確認這是測試模式
            assert write_back is False
            yield MigrateProgress(
                resource_id="user:1", status="success", message="Test success"
            )
            yield MigrateProgress(
                resource_id="user:2", status="skipped", message="Already migrated"
            )
            yield MigrateProgress(
                resource_id="user:3", status="failed", error="Test error"
            )

        with patch.object(
            MigrateRouteTemplate,
            "_migrate_resources_generator",
            side_effect=mock_generator,
        ):
            with client.websocket_connect("/user/migrate/test") as websocket:
                # 發送查詢條件
                websocket.send_json({"query": {"limit": 10, "offset": 0}})

                # 接收進度訊息
                messages: List[Dict[str, Any]] = []
                # 接收所有訊息直到連線關閉
                while True:
                    try:
                        message = websocket.receive_text()
                        data = json.loads(message)
                        messages.append(data)
                        # 如果收到最終結果就停止
                        if "total" in data:
                            break
                    except Exception:
                        break

                # 驗證訊息結構
                assert len(messages) == 4  # 3 個進度 + 1 個結果

                # 檢查進度訊息
                progress_messages = messages[:3]
                for i, progress in enumerate(progress_messages):
                    assert "resource_id" in progress
                    assert "status" in progress
                    assert progress["resource_id"] == f"user:{i + 1}"

                # 檢查最終結果
                result = messages[3]
                assert "total" in result
                assert result["total"] == 3
                assert result["success"] == 1
                assert result["failed"] == 1
                assert result["skipped"] == 1
                assert len(result["errors"]) == 1

    def test_websocket_execute_migration_success(self, client: TestClient) -> None:
        """測試 WebSocket 執行遷移成功"""

        # Mock the generator to return execution results
        async def mock_generator(
            manager: Mock, query: Any, user: str, time: dt.datetime, write_back: bool
        ) -> AsyncGenerator[MigrateProgress, None]:
            # 確認這是執行模式
            assert write_back is True
            yield MigrateProgress(
                resource_id="user:1", status="success", message="Migrated successfully"
            )
            yield MigrateProgress(
                resource_id="user:2", status="success", message="Migrated successfully"
            )

        with patch.object(
            MigrateRouteTemplate,
            "_migrate_resources_generator",
            side_effect=mock_generator,
        ):
            with client.websocket_connect("/user/migrate/execute") as websocket:
                # 發送空查詢（遷移所有資源）
                websocket.send_json({})

                # 接收訊息
                messages: List[Dict[str, Any]] = []
                while True:
                    try:
                        message = websocket.receive_text()
                        data = json.loads(message)
                        messages.append(data)
                        # 如果收到最終結果就停止
                        if "total" in data:
                            break
                    except Exception:
                        break

                # 驗證結果
                assert len(messages) == 3  # 2 個進度 + 1 個結果

                # 檢查最終結果
                result = messages[2]
                assert result["total"] == 2
                assert result["success"] == 2
                assert result["failed"] == 0
                assert result["skipped"] == 0


class TestMigrateRouteTemplate:
    """測試 MigrateRouteTemplate 類別"""

    def test_migrate_route_template_initialization(self) -> None:
        """測試 MigrateRouteTemplate 初始化"""
        template = MigrateRouteTemplate()
        assert template is not None
        assert hasattr(template, "apply")
        assert hasattr(template, "_migrate_single_resource")
        assert hasattr(template, "_migrate_resources_generator")

    def test_migrate_route_template_apply(self, mock_resource_manager: Mock) -> None:
        """測試 apply 方法正確註冊路由"""
        router = APIRouter()
        template = MigrateRouteTemplate()

        # 應用路由前確認沒有路由
        assert len(router.routes) == 0

        # 應用路由
        template.apply("user", mock_resource_manager, router)

        # 檢查路由數量
        assert len(router.routes) == 3

        # 檢查路由類型和路徑
        route_info: List[Dict[str, Any]] = []
        for route in router.routes:
            if hasattr(route, "path") and hasattr(route, "methods"):
                # HTTP 路由
                route_info.append(
                    {"type": "http", "path": route.path, "methods": route.methods}
                )
            elif hasattr(route, "path"):
                # WebSocket 路由
                route_info.append({"type": "websocket", "path": route.path})

        # 驗證具體路由
        http_routes = [r for r in route_info if r["type"] == "http"]
        ws_routes = [r for r in route_info if r["type"] == "websocket"]

        # 應該有 1 個 HTTP 路由和 2 個 WebSocket 路由
        assert len(http_routes) == 1
        assert len(ws_routes) == 2

        # 檢查 HTTP 路由
        assert http_routes[0]["path"] == "/user/migrate/single/{resource_id}"
        assert "POST" in http_routes[0]["methods"]

        # 檢查 WebSocket 路由
        ws_paths = [r["path"] for r in ws_routes]
        assert "/user/migrate/test" in ws_paths
        assert "/user/migrate/execute" in ws_paths


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
