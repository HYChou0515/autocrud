"""測試 MigrateProgress 和 MigrateResult 是否出現在 OpenAPI schema 中"""

import msgspec
import pytest
from fastapi import FastAPI

from autocrud import AutoCRUD, Schema
from autocrud.crud.route_templates.migrate import MigrateRouteTemplate


class ItemV1(msgspec.Struct):
    name: str


class ItemV2(msgspec.Struct):
    name: str
    tag: str = "none"


def migrate_v1_to_v2(data: dict) -> dict:
    data.setdefault("tag", "none")
    return data


class TestMigrateProgressInOpenAPI:
    """確認啟用 migrate route 後，MigrateProgress 和 MigrateResult 出現在 OpenAPI components/schemas"""

    @pytest.fixture()
    def app_with_migrate(self) -> FastAPI:
        app = FastAPI()
        crud = AutoCRUD()

        schema = Schema(ItemV2, "v2").step("v1", migrate_v1_to_v2)
        crud.add_model(schema)
        crud.add_route_template(MigrateRouteTemplate())
        crud.apply(app)
        crud.openapi(app)
        return app

    def test_migrate_progress_in_openapi_components(self, app_with_migrate: FastAPI):
        """MigrateProgress 應出現在 components/schemas 中"""
        schemas = app_with_migrate.openapi_schema["components"]["schemas"]
        assert "MigrateProgress" in schemas, (
            f"MigrateProgress not found in OpenAPI components/schemas. "
            f"Available schemas: {sorted(schemas.keys())}"
        )

    def test_migrate_result_in_openapi_components(self, app_with_migrate: FastAPI):
        """MigrateResult 應出現在 components/schemas 中"""
        schemas = app_with_migrate.openapi_schema["components"]["schemas"]
        assert "MigrateResult" in schemas, (
            f"MigrateResult not found in OpenAPI components/schemas. "
            f"Available schemas: {sorted(schemas.keys())}"
        )

    def test_migrate_progress_schema_has_required_fields(
        self, app_with_migrate: FastAPI
    ):
        """MigrateProgress schema 應包含 resource_id 和 status 必填欄位"""
        schemas = app_with_migrate.openapi_schema["components"]["schemas"]
        if "MigrateProgress" not in schemas:
            pytest.skip(
                "MigrateProgress not yet in OpenAPI (test_migrate_progress_in_openapi_components should fail first)"
            )

        progress_schema = schemas["MigrateProgress"]
        assert "properties" in progress_schema
        assert "resource_id" in progress_schema["properties"]
        assert "status" in progress_schema["properties"]
        assert "resource_id" in progress_schema.get("required", [])
        assert "status" in progress_schema.get("required", [])

    def test_migrate_result_schema_has_required_fields(self, app_with_migrate: FastAPI):
        """MigrateResult schema 應包含 total, success, failed, skipped 必填欄位"""
        schemas = app_with_migrate.openapi_schema["components"]["schemas"]
        if "MigrateResult" not in schemas:
            pytest.skip(
                "MigrateResult not yet in OpenAPI (test_migrate_result_in_openapi_components should fail first)"
            )

        result_schema = schemas["MigrateResult"]
        assert "properties" in result_schema
        for field in ("total", "success", "failed", "skipped"):
            assert field in result_schema["properties"], f"Missing field: {field}"
        required = result_schema.get("required", [])
        for field in ("total", "success", "failed", "skipped"):
            assert field in required, f"Field '{field}' should be required"
