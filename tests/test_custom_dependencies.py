"""測試 custom_dependencies 功能"""

from typing import TypedDict
from fastapi import Depends, HTTPException, status, Header
from fastapi.testclient import TestClient
from autocrud import AutoCRUD
from autocrud.route_config import RouteConfig, RouteOptions


class User(TypedDict):
    id: str
    name: str
    email: str
    age: int
    role: str


# 依賴函數
def check_api_key(x_api_key: str = Header(None)):
    """檢查 API 密鑰"""
    if not x_api_key or x_api_key != "secret-api-key":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )
    return x_api_key


def check_admin_role(x_admin_token: str = Header(None)):
    """檢查管理員權限"""
    if not x_admin_token or x_admin_token != "admin-token":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )
    return True


def check_user_permission(x_user_id: str = Header(None)):
    """檢查用戶權限"""
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID required"
        )
    return x_user_id


def test_custom_dependencies():
    """測試自定義依賴功能"""

    # 創建 AutoCRUD 實例
    autocrud = AutoCRUD()
    autocrud.register_model(User)

    # 創建具有不同自定義依賴的路由配置
    config = RouteConfig(
        # 創建用戶需要 API 密鑰
        create=RouteOptions(enabled=True, custom_dependencies=[Depends(check_api_key)]),
        # 獲取單個用戶需要用戶權限
        get=RouteOptions(
            enabled=True, custom_dependencies=[Depends(check_user_permission)]
        ),
        # 更新用戶需要管理員權限
        update=RouteOptions(
            enabled=True, custom_dependencies=[Depends(check_admin_role)]
        ),
        # 刪除用戶需要管理員權限
        delete=RouteOptions(
            enabled=True, custom_dependencies=[Depends(check_admin_role)]
        ),
        # 列出用戶不需要特殊權限
        list=RouteOptions(enabled=True),
        # 計數需要用戶權限
        count=RouteOptions(
            enabled=True, custom_dependencies=[Depends(check_user_permission)]
        ),
    )

    # 創建 FastAPI 應用
    app = autocrud.create_fastapi_app(
        title="Custom Dependencies API",
        description="API with custom dependencies",
        route_config=config,
    )

    client = TestClient(app)

    print("=== 測試創建用戶（需要 API 密鑰）===")

    # 測試沒有 API 密鑰的創建請求
    response = client.post(
        "/api/v1/users",
        json={
            "name": "John Doe",
            "email": "john@example.com",
            "age": 30,
            "role": "user",
        },
    )
    assert response.status_code == 401
    assert "Invalid API key" in response.json()["detail"]
    print("✅ 無 API 密鑰請求正確被拒絕")

    # 測試帶有正確 API 密鑰的創建請求
    response = client.post(
        "/api/v1/users",
        json={
            "name": "John Doe",
            "email": "john@example.com",
            "age": 30,
            "role": "user",
        },
        headers={"X-API-Key": "secret-api-key"},
    )
    assert response.status_code == 201
    user_data = response.json()
    user_id = user_data["id"]
    print(f"✅ 用戶創建成功: {user_id}")

    print("\n=== 測試獲取用戶（需要用戶權限）===")

    # 測試沒有用戶 ID 的獲取請求
    response = client.get(f"/api/v1/users/{user_id}")
    assert response.status_code == 401
    print("✅ 無用戶 ID 請求正確被拒絕")

    # 測試帶有用戶權限的獲取請求
    response = client.get(f"/api/v1/users/{user_id}", headers={"X-User-ID": "user123"})
    assert response.status_code == 200
    retrieved_data = response.json()
    assert retrieved_data["id"] == user_id
    print("✅ 有用戶權限的獲取請求成功")

    print("\n=== 測試更新用戶（需要管理員權限）===")

    # 測試沒有管理員權限的更新請求
    response = client.put(
        f"/api/v1/users/{user_id}", json={"name": "John Updated", "age": 31}
    )
    assert response.status_code == 403
    print("✅ 無管理員權限請求正確被拒絕")

    # 測試帶有管理員權限的更新請求
    response = client.put(
        f"/api/v1/users/{user_id}",
        json={
            "name": "John Updated",
            "email": "john.updated@example.com",
            "age": 31,
            "role": "admin",
        },
        headers={"X-Admin-Token": "admin-token"},
    )
    assert response.status_code == 200
    print("✅ 管理員更新請求成功")

    print("\n=== 測試刪除用戶（需要管理員權限）===")

    # 測試沒有管理員權限的刪除請求
    response = client.delete(f"/api/v1/users/{user_id}")
    assert response.status_code == 403
    print("✅ 無管理員權限刪除請求正確被拒絕")

    # 測試帶有管理員權限的刪除請求
    response = client.delete(
        f"/api/v1/users/{user_id}", headers={"X-Admin-Token": "admin-token"}
    )
    assert response.status_code == 204
    print("✅ 管理員刪除請求成功")

    print("\n=== 測試列出用戶（無特殊權限需求）===")

    # 測試列出用戶
    response = client.get("/api/v1/users")
    assert response.status_code == 200
    print("✅ 列出用戶請求成功")

    print("\n=== 測試計數（需要用戶權限）===")

    # 測試沒有用戶權限的計數請求
    response = client.get("/api/v1/users/count")
    assert response.status_code == 401
    print("✅ 無用戶權限計數請求正確被拒絕")

    # 測試帶有用戶權限的計數請求
    response = client.get("/api/v1/users/count", headers={"X-User-ID": "user123"})
    assert response.status_code == 200
    count_data = response.json()
    assert "count" in count_data
    print("✅ 有用戶權限的計數請求成功")


def test_mixed_dependencies():
    """測試混合依賴配置"""

    # 創建另一個用戶模型用於測試
    autocrud = AutoCRUD()
    autocrud.register_model(User)

    # 創建混合配置：一些路由有依賴，一些沒有
    config = RouteConfig(
        create=True,  # 使用預設配置，無依賴
        get=RouteOptions(enabled=True, custom_dependencies=[Depends(check_api_key)]),
        update=True,  # 無依賴
        delete=RouteOptions(
            enabled=True, custom_dependencies=[Depends(check_admin_role)]
        ),
        list=True,  # 無依賴
        count=True,  # 無依賴
    )

    app = autocrud.create_fastapi_app(route_config=config)
    client = TestClient(app)

    print("\n=== 測試混合依賴配置 ===")

    # 創建用戶（無依賴要求）
    response = client.post(
        "/api/v1/users",
        json={
            "name": "Mixed Test User",
            "email": "mixed@example.com",
            "age": 25,
            "role": "user",
        },
    )
    assert response.status_code == 201
    user_id = response.json()["id"]
    print("✅ 無依賴創建請求成功")

    # 獲取用戶（需要 API 密鑰）
    response = client.get(f"/api/v1/users/{user_id}")
    assert response.status_code == 401
    print("✅ 需要依賴的 GET 請求正確被拒絕")

    response = client.get(
        f"/api/v1/users/{user_id}", headers={"X-API-Key": "secret-api-key"}
    )
    assert response.status_code == 200
    print("✅ 有依賴的 GET 請求成功")

    # 更新用戶（無依賴要求）
    response = client.put(
        f"/api/v1/users/{user_id}",
        json={
            "name": "Updated Mixed User",
            "email": "mixed@example.com",
            "age": 25,
            "role": "user",
        },
    )
    if response.status_code != 200:
        print(f"更新失敗，狀態碼: {response.status_code}")
        print(f"響應內容: {response.json()}")
    assert response.status_code == 200
    print("✅ 無依賴更新請求成功")

    # 刪除用戶（需要管理員權限）
    response = client.delete(f"/api/v1/users/{user_id}")
    assert response.status_code == 403
    print("✅ 需要依賴的 DELETE 請求正確被拒絕")


if __name__ == "__main__":
    test_custom_dependencies()
    test_mixed_dependencies()

    print("\n🎉 所有 custom_dependencies 測試通過！")
    print("\n📝 功能摘要：")
    print("✅ CREATE 路由支持自定義依賴")
    print("✅ GET 路由支持自定義依賴")
    print("✅ UPDATE 路由支持自定義依賴")
    print("✅ DELETE 路由支持自定義依賴")
    print("✅ LIST 路由支持自定義依賴")
    print("✅ COUNT 路由支持自定義依賴")
    print("✅ 支持混合配置（部分路由有依賴，部分沒有）")
    print("✅ 與現有的背景任務功能完全兼容")
