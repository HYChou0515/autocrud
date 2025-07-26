"""
資源名稱命名風格示例

展示如何使用不同的資源名稱命名風格 (snake_case, camelCase, dash-case)
"""

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
    employees: int


@dataclass
class ProductCategory:
    id: str
    category_name: str
    description: str
    is_active: bool


def main():
    print("=== 資源名稱命名風格示例 ===\n")

    # 1. Snake Case (預設)
    print("1. Snake Case 風格 (預設):")
    autocrud_snake = AutoCRUD(resource_name_style=ResourceNameStyle.SNAKE)

    autocrud_snake.register_model(UserProfile)
    autocrud_snake.register_model(CompanyInfo)
    autocrud_snake.register_model(ProductCategory)

    print("   註冊的資源:")
    for resource_name in autocrud_snake.list_resources():
        print(f"   - {resource_name}")
    print()

    # 2. Camel Case
    print("2. Camel Case 風格:")
    autocrud_camel = AutoCRUD(resource_name_style=ResourceNameStyle.CAMEL)

    autocrud_camel.register_model(UserProfile)
    autocrud_camel.register_model(CompanyInfo)
    autocrud_camel.register_model(ProductCategory)

    print("   註冊的資源:")
    for resource_name in autocrud_camel.list_resources():
        print(f"   - {resource_name}")
    print()

    # 3. Dash Case
    print("3. Dash Case 風格:")
    autocrud_dash = AutoCRUD(resource_name_style=ResourceNameStyle.DASH)

    autocrud_dash.register_model(UserProfile)
    autocrud_dash.register_model(CompanyInfo)
    autocrud_dash.register_model(ProductCategory)

    print("   註冊的資源:")
    for resource_name in autocrud_dash.list_resources():
        print(f"   - {resource_name}")
    print()

    # 4. 混合使用和覆蓋
    print("4. 混合使用和單獨覆蓋:")
    autocrud_mixed = AutoCRUD(resource_name_style=ResourceNameStyle.SNAKE)

    # 使用預設風格
    autocrud_mixed.register_model(UserProfile)

    # 覆蓋為 camel 風格
    autocrud_mixed.register_model(
        CompanyInfo, resource_name_style=ResourceNameStyle.CAMEL
    )

    # 覆蓋為 dash 風格且單數
    autocrud_mixed.register_model(
        ProductCategory, use_plural=False, resource_name_style=ResourceNameStyle.DASH
    )

    print("   註冊的資源:")
    for resource_name in autocrud_mixed.list_resources():
        print(f"   - {resource_name}")
    print()

    # 5. 實際操作示例
    print("5. 實際 CRUD 操作:")

    # 使用 camelCase 風格
    autocrud = AutoCRUD(resource_name_style=ResourceNameStyle.CAMEL)
    autocrud.register_model(UserProfile)
    autocrud.register_model(CompanyInfo)

    # 創建用戶
    user_id = autocrud.create(
        "userProfiles",
        {"id": "user1", "name": "張三", "email": "zhang@example.com", "age": 28},
    )
    print(f"   創建用戶 ID: {user_id}")

    # 創建公司
    company_id = autocrud.create(
        "companyInfos",
        {
            "id": "company1",
            "company_name": "科技公司",
            "industry": "軟體開發",
            "employees": 50,
        },
    )
    print(f"   創建公司 ID: {company_id}")

    # 獲取數據
    user = autocrud.get("userProfiles", user_id)
    company = autocrud.get("companyInfos", company_id)

    print(f"   用戶資料: {user['name']} ({user['email']})")
    print(f"   公司資料: {company['company_name']} - {company['industry']}")
    print()

    # 6. FastAPI 路由生成
    print("6. FastAPI 路由示例:")

    # 不同風格的路由路徑
    styles = [
        (ResourceNameStyle.SNAKE, "snake_case"),
        (ResourceNameStyle.CAMEL, "camelCase"),
        (ResourceNameStyle.DASH, "dash-case"),
    ]

    for style, style_name in styles:
        autocrud_style = AutoCRUD(resource_name_style=style)
        user_crud_result = autocrud_style.register_model(UserProfile)

        # 生成 FastAPI 路由
        from autocrud.fastapi_generator import FastAPIGenerator

        generator = FastAPIGenerator(user_crud_result)
        router = generator.create_router()

        print(f"   {style_name} 風格的路由:")
        for route in router.routes:
            if hasattr(route, "path") and route.path != "/":
                print(f"     {route.methods} {route.path}")
        print()


if __name__ == "__main__":
    main()
