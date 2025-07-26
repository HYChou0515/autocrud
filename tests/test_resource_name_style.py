"""測試資源名稱命名風格功能"""

from dataclasses import dataclass
from autocrud import AutoCRUD, ResourceNameStyle


@dataclass
class UserProfile:
    id: str
    name: str
    email: str
    age: int


@dataclass
class CompanyInfo:
    id: str
    company_name: str
    industry: str


@dataclass
class ProductCategory:
    id: str
    category_name: str
    description: str


class TestResourceNameStyle:
    """測試資源名稱命名風格"""

    def test_snake_case_style(self):
        """測試 snake_case 風格（預設）"""
        autocrud = AutoCRUD(resource_name_style=ResourceNameStyle.SNAKE)

        # 測試複數形式
        autocrud.register_model(UserProfile)
        assert "user_profiles" in autocrud.cruds

        # 測試單數形式
        autocrud.register_model(CompanyInfo, use_plural=False)
        assert "company_info" in autocrud.cruds

        # 測試複雜的複數化規則
        autocrud.register_model(ProductCategory)
        assert (
            "product_categories" in autocrud.cruds
        )  # y -> ies    def test_camel_case_style(self):
        """測試 camelCase 風格"""
        autocrud = AutoCRUD(resource_name_style=ResourceNameStyle.CAMEL)

        # 測試複數形式
        autocrud.register_model(UserProfile)
        assert "userProfiles" in autocrud.cruds

        # 測試單數形式
        autocrud.register_model(CompanyInfo, use_plural=False)
        assert "companyInfo" in autocrud.cruds

        # 測試複雜的複數化規則
        autocrud.register_model(ProductCategory)
        assert "productCategories" in autocrud.cruds

    def test_dash_case_style(self):
        """測試 dash-case 風格"""
        autocrud = AutoCRUD(resource_name_style=ResourceNameStyle.DASH)

        # 測試複數形式
        autocrud.register_model(UserProfile)
        assert "user-profiles" in autocrud.cruds

        # 測試單數形式
        autocrud.register_model(CompanyInfo, use_plural=False)
        assert "company-info" in autocrud.cruds

        # 測試複雜的複數化規則
        autocrud.register_model(ProductCategory)
        assert "product-categories" in autocrud.cruds

    def test_override_style_per_model(self):
        """測試每個模型可以覆蓋預設風格"""
        # 預設使用 snake_case
        autocrud = AutoCRUD(resource_name_style=ResourceNameStyle.SNAKE)

        # 使用預設風格
        autocrud.register_model(UserProfile)
        assert "user_profiles" in autocrud.cruds

        # 覆蓋為 camel 風格
        autocrud.register_model(
            CompanyInfo, resource_name_style=ResourceNameStyle.CAMEL
        )
        assert "companyInfos" in autocrud.cruds

        # 覆蓋為 dash 風格且單數
        autocrud.register_model(
            ProductCategory,
            use_plural=False,
            resource_name_style=ResourceNameStyle.DASH,
        )
        assert "product-category" in autocrud.cruds

    def test_explicit_resource_name_ignores_style(self):
        """測試明確指定資源名稱會忽略命名風格"""
        autocrud = AutoCRUD(resource_name_style=ResourceNameStyle.CAMEL)

        # 明確指定資源名稱
        autocrud.register_model(UserProfile, resource_name="custom_users")
        assert "custom_users" in autocrud.cruds
        assert "userProfiles" not in autocrud.cruds

    def test_crud_operations_work_with_different_styles(self):
        """測試不同命名風格下 CRUD 操作正常工作"""
        # 測試 camelCase
        autocrud_camel = AutoCRUD(resource_name_style=ResourceNameStyle.CAMEL)
        autocrud_camel.register_model(UserProfile)

        # 創建用戶
        user_id = autocrud_camel.create(
            "userProfiles",
            {
                "id": "user1",
                "name": "Test User",
                "email": "test@example.com",
                "age": 25,
            },
        )

        # 獲取用戶
        user = autocrud_camel.get("userProfiles", user_id)
        assert user["name"] == "Test User"

        # 測試 dash-case
        autocrud_dash = AutoCRUD(resource_name_style=ResourceNameStyle.DASH)
        autocrud_dash.register_model(CompanyInfo)

        # 創建公司
        company_id = autocrud_dash.create(
            "company-infos",
            {"id": "company1", "company_name": "Test Corp", "industry": "Tech"},
        )

        # 獲取公司
        company = autocrud_dash.get("company-infos", company_id)
        assert company["company_name"] == "Test Corp"

    def test_pluralization_rules(self):
        """測試不同的複數化規則"""

        @dataclass
        class City:
            id: str
            name: str

        @dataclass
        class Box:
            id: str
            size: str

        @dataclass
        class Patch:
            id: str
            version: str

        autocrud = AutoCRUD()

        # 一般情況：加 s
        autocrud.register_model(City)
        assert "cities" in autocrud.cruds  # y -> ies

        # 以 x 結尾：加 es
        autocrud.register_model(Box)
        assert "boxes" in autocrud.cruds

        # 以 ch 結尾：加 es
        autocrud.register_model(Patch)
        assert "patches" in autocrud.cruds


class TestResourceNameStyleIntegration:
    """測試資源名稱風格與其他功能的集成"""

    def test_fastapi_routes_with_different_styles(self):
        """測試不同命名風格生成的 FastAPI 路由"""
        from autocrud.fastapi_generator import FastAPIGenerator

        # camelCase 風格
        autocrud_camel = AutoCRUD(resource_name_style=ResourceNameStyle.CAMEL)
        user_crud_result = autocrud_camel.register_model(UserProfile)

        generator = FastAPIGenerator(user_crud_result)
        router = generator.create_router()

        # 檢查路由路徑
        routes = [route.path for route in router.routes]
        assert "/userProfiles" in routes
        assert "/userProfiles/{resource_id}" in routes
        assert "/userProfiles/count" in routes

        # dash-case 風格
        autocrud_dash = AutoCRUD(resource_name_style=ResourceNameStyle.DASH)
        company_crud_result = autocrud_dash.register_model(CompanyInfo)

        generator_dash = FastAPIGenerator(company_crud_result)
        router_dash = generator_dash.create_router()

        routes_dash = [route.path for route in router_dash.routes]
        assert "/company-infos" in routes_dash
        assert "/company-infos/{resource_id}" in routes_dash
        assert "/company-infos/count" in routes_dash

    def test_create_fastapi_app_with_styles(self):
        """測試使用不同命名風格創建 FastAPI 應用"""
        autocrud = AutoCRUD(resource_name_style=ResourceNameStyle.DASH)
        autocrud.register_model(UserProfile)
        autocrud.register_model(CompanyInfo)

        app = autocrud.create_fastapi_app()

        # 檢查應用中的路由
        all_routes = []
        for route in app.routes:
            if hasattr(route, "path"):
                all_routes.append(route.path)
            elif hasattr(route, "routes"):  # APIRouter
                for subroute in route.routes:
                    if hasattr(subroute, "path"):
                        all_routes.append(subroute.path)

        # 應該包含 dash-case 的路由
        assert any("user-profiles" in route for route in all_routes)
        assert any("company-infos" in route for route in all_routes)
