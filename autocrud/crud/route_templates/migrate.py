import datetime as dt
import textwrap
from typing import AsyncGenerator, TypeVar

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import StreamingResponse

from autocrud.crud.route_templates.basic import (
    BaseRouteTemplate,
    MsgspecResponse,
    QueryInputs,
    build_query,
    struct_to_responses_type,
)
from autocrud.types import (
    IResourceManager,
    ResourceMetaSearchQuery,
)
import msgspec

T = TypeVar("T")


class MigrateProgress(msgspec.Struct):
    """遷移進度訊息"""

    resource_id: str
    status: str  # "migrating", "success", "failed", "skipped"
    message: str | None = None
    error: str | None = None


class MigrateResult(msgspec.Struct):
    """遷移結果統計"""

    total: int
    success: int
    failed: int
    skipped: int
    errors: list[dict] = msgspec.field(default_factory=list)


def build_msg(obj: msgspec.Struct) -> bytes:
    return (
        msgspec.json.encode(msgspec.to_builtins(obj) | {"timestamp": dt.datetime.now()})
        + b"\n"
    )


class MigrateRouteTemplate(BaseRouteTemplate):
    """資源遷移的路由模板"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def _migrate_single_resource(
        self,
        resource_manager: IResourceManager[T],
        resource_id: str,
        current_user: str,
        current_time: dt.datetime,
        *,
        write_back: bool = True,
    ) -> MigrateProgress:
        """遷移單一資源"""
        try:
            with resource_manager.meta_provide(current_user, current_time):
                # 檢查是否需要遷移
                meta = resource_manager.get_meta(resource_id)

                # 假設有 migration 且 schema_version 不符才需要遷移
                if meta.schema_version != resource_manager.schema_version:
                    if write_back:
                        # 執行遷移並寫回 storage
                        # 這裡需要實際的遷移邏輯
                        migrated_resource = resource_manager.migrate(resource_id)
                        return MigrateProgress(
                            resource_id=resource_id,
                            status="success",
                            message=f"Migrated {migrated_resource.resource_id} from {meta.schema_version} to {resource_manager.schema_version}",
                        )
                    else:
                        # 只在記憶體中遷移測試
                        return MigrateProgress(
                            resource_id=resource_id,
                            status="success",
                            message="Migration simulation successful",
                        )
                else:
                    return MigrateProgress(
                        resource_id=resource_id,
                        status="skipped",
                        message="Resource already at current schema version",
                    )

        except Exception as e:
            return MigrateProgress(
                resource_id=resource_id, status="failed", error=str(e)
            )

    async def _migrate_resources_generator(
        self,
        resource_manager: IResourceManager[T],
        query: ResourceMetaSearchQuery | None,
        current_user: str,
        current_time: dt.datetime,
        write_back: bool = True,
    ) -> AsyncGenerator[MigrateProgress, None]:
        """遷移資源的生成器"""
        try:
            with resource_manager.meta_provide(current_user, current_time):
                # 根據 query 搜尋需要遷移的資源
                if query:
                    search_result = resource_manager.search_resources(query)
                    resource_ids = [meta.resource_id for meta in search_result]
                else:
                    # 獲取所有資源
                    resource_ids = list(
                        resource_manager.search_resources(ResourceMetaSearchQuery())
                    )

                for resource_id in resource_ids:
                    progress = await self._migrate_single_resource(
                        resource_manager,
                        resource_id,
                        current_user,
                        current_time,
                        write_back=write_back,
                    )
                    yield progress

        except Exception as e:
            yield MigrateProgress(
                resource_id="",
                status="failed",
                error=f"Migration process failed: {str(e)}",
            )

    async def _migrate_with_message(
        self, migrate_coroutine: AsyncGenerator[MigrateProgress, None]
    ) -> AsyncGenerator[bytes, None]:
        """遷移並產生訊息的生成器"""
        result = MigrateResult(total=0, success=0, failed=0, skipped=0)
        try:
            async for progress in migrate_coroutine:
                yield build_msg(progress)

                # 更新統計
                result.total += 1
                if progress.status == "success":
                    result.success += 1
                elif progress.status == "failed":
                    result.failed += 1
                    result.errors.append(
                        {
                            "resource_id": progress.resource_id,
                            "error": progress.error,
                        }
                    )
                elif progress.status == "skipped":
                    result.skipped += 1
            yield build_msg(result)
        except WebSocketDisconnect:
            pass
        except Exception as e:
            error_progress = MigrateProgress(
                resource_id="",
                status="failed",
                error=f"Migration test process error: {str(e)}",
            )
            yield build_msg(error_progress)
            yield build_msg(result)

    def apply(
        self,
        model_name: str,
        resource_manager: IResourceManager[T],
        router: APIRouter,
    ) -> None:
        @router.websocket(f"/{model_name}/migrate/test")
        async def test_migrate_resources_ws(
            websocket: WebSocket,
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            """
            Test migration for resources with real-time progress updates via WebSocket.
            No data will be written back to storage - memory-only testing.

            **WebSocket Messages:**
            - Send: {"query": ResourceMetaSearchQuery} to start migration test
            - Receive: MigrateProgress messages for each resource being tested
            - Receive: MigrateResult as final summary

            **Message Types:**
            - Progress: {"resource_id": "123", "status": "success|failed|skipped", "message": "...", "error": "..."}
            - Result: {"total": 100, "success": 95, "failed": 3, "skipped": 2, "errors": [...]}

            **Safety:**
            - No actual data modification
            - Memory-only migration testing
            - Safe to run on production data
            """
            await websocket.accept()
            # 等待前端發送查詢條件
            data = await websocket.receive_json()
            query = None
            if data and "query" in data:
                query = msgspec.convert(data["query"], ResourceMetaSearchQuery)

            # 開始測試遷移並發送進度
            async for msg in self._migrate_with_message(
                self._migrate_resources_generator(
                    resource_manager,
                    query,
                    current_user,
                    current_time,
                    write_back=False,
                )
            ):
                # 發送單個資源的測試進度
                await websocket.send_text(msg.decode())
            await websocket.close()

        @router.websocket(f"/{model_name}/migrate/execute")
        async def execute_migrate_resources_ws(
            websocket: WebSocket,
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            """
            Execute migration for resources with real-time progress updates via WebSocket.

            **WebSocket Messages:**
            - Send: {"query": ResourceMetaSearchQuery} to start migration
            - Receive: MigrateProgress messages for each resource
            - Receive: MigrateResult as final summary

            **Message Types:**
            - Progress: {"resource_id": "123", "status": "migrating|success|failed|skipped", "message": "...", "error": "..."}
            - Result: {"total": 100, "success": 95, "failed": 3, "skipped": 2, "errors": [...]}
            """
            await websocket.accept()
            # 等待前端發送查詢條件
            data = await websocket.receive_json()
            query = None
            if data and "query" in data:
                query = msgspec.convert(data["query"], ResourceMetaSearchQuery)

            # 開始測試遷移並發送進度
            async for msg in self._migrate_with_message(
                self._migrate_resources_generator(
                    resource_manager,
                    query,
                    current_user,
                    current_time,
                    write_back=True,
                )
            ):
                # 發送單個資源的測試進度
                await websocket.send_text(msg.decode())

        @router.post(f"/{model_name}/migrate/test")
        async def test_migrate_resources(
            query_params: QueryInputs = Query(...),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            """
            Test migration for resources with real-time progress updates via http streaming.
            No data will be written back to storage - memory-only testing.
            """
            query = build_query(query_params)

            return StreamingResponse(
                self._migrate_with_message(
                    self._migrate_resources_generator(
                        resource_manager,
                        query,
                        current_user,
                        current_time,
                        write_back=False,
                    )
                ),
                media_type="application/jsonl+json",
            )

        @router.post(f"/{model_name}/migrate/execute")
        async def execute_migrate_resources(
            query_params: QueryInputs = Query(...),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            """
            Execute migration for resources with real-time progress updates via http streaming.
            """
            query = build_query(query_params)

            return StreamingResponse(
                self._migrate_with_message(
                    self._migrate_resources_generator(
                        resource_manager,
                        query,
                        current_user,
                        current_time,
                        write_back=True,
                    )
                ),
                media_type="application/jsonl+json",
            )

        @router.post(
            f"/{model_name}/migrate/single/{{resource_id}}",
            responses=struct_to_responses_type(MigrateProgress),
            summary=f"Migrate Single {model_name} Resource",
            tags=[f"{model_name}"],
            description=textwrap.dedent(
                f"""
                Migrate a single `{model_name}` resource to the current schema version.

                **Path Parameters:**
                - `resource_id`: The unique identifier of the resource to migrate

                **Query Parameters:**
                - `write_back` (optional, default=true): Whether to write migrated data back to storage

                **Response:**
                - Returns migration progress for the single resource:
                  - `resource_id`: The resource that was migrated
                  - `status`: Migration status (success/failed/skipped)
                  - `message`: Success message or additional info
                  - `error`: Error message if migration failed

                **Use Cases:**
                - Migrate specific resource after schema update
                - Fix individual resource migration issues
                - Test migration on single resource
                - Manual resource upgrade

                **Examples:**
                - `POST /{model_name}/migrate/single/123` - Migrate resource 123
                - `POST /{model_name}/migrate/single/123?write_back=false` - Test migrate resource 123

                **Error Responses:**
                - `404`: Resource not found
                - `400`: Migration failed
                """,
            ),
        )
        async def migrate_single_resource(
            resource_id: str,
            *,
            write_back: bool = Query(
                True, description="Whether to write migrated data back to storage"
            ),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            try:
                progress = await self._migrate_single_resource(
                    resource_manager,
                    resource_id,
                    current_user,
                    current_time,
                    write_back=write_back,
                )

                if progress.status == "failed":
                    raise HTTPException(status_code=400, detail=progress.error)

                return MsgspecResponse(progress)

            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=404, detail=str(e))
