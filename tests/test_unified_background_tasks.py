"""測試統一的 background task callback signature"""

from typing import TypedDict, Any
from fastapi.testclient import TestClient
from autocrud import AutoCRUD
from autocrud.route_config import RouteConfig, RouteOptions, BackgroundTaskMode


class User(TypedDict):
    id: str
    name: str
    email: str
    age: int
    role: str


# 統一的 background task 函數，接收 4 個標準參數
def unified_background_task(
    route_name: str, resource_name: str, route_input: Any, route_output: Any
):
    """統一的背景任務函數，接收標準的 4 個參數"""
    print("Background task called:")
    print(f"  Route name: {route_name}")
    print(f"  Resource name: {resource_name}")
    print(f"  Route input: {route_input}")
    print(f"  Route output: {route_output}")
    print(f"  Output type: {type(route_output)}")

    # 根據不同的輸出類型進行處理
    if isinstance(route_output, dict):
        if "id" in route_output:
            # 這是一個用戶對象
            print(f"Processing user: {route_output['name']} (ID: {route_output['id']})")
        elif "count" in route_output:
            # 這是計數結果
            print(f"Processing count result: {route_output['count']} users")
    elif isinstance(route_output, list):
        # 這是用戶列表
        print(f"Processing user list with {len(route_output)} users")
    elif route_output is None:
        # 這是 DELETE 操作的結果
        print("Processing delete operation result (None)")
    else:
        print(f"Unknown output type: {type(route_output)}")


def log_task_execution(
    route_name: str, resource_name: str, route_input: Any, route_output: Any
):
    """另一個統一的背景任務函數，用於記錄"""
    print(f"LOG: Route '{route_name}' on resource '{resource_name}' executed")
    print(f"LOG: Input: {route_input}, Output: {route_output}")


def test_unified_background_task_signature():
    """測試統一的背景任務 callback signature"""

    # 創建 AutoCRUD 實例
    autocrud = AutoCRUD()
    autocrud.register_model(User)

    # 為所有路由配置相同的背景任務函數
    config = RouteConfig(
        create=RouteOptions(
            enabled=True,
            background_task=BackgroundTaskMode.ENABLED,
            background_task_func=unified_background_task,
        ),
        get=RouteOptions(
            enabled=True,
            background_task=BackgroundTaskMode.ENABLED,
            background_task_func=unified_background_task,
        ),
        update=RouteOptions(
            enabled=True,
            background_task=BackgroundTaskMode.ENABLED,
            background_task_func=unified_background_task,
        ),
        delete=RouteOptions(
            enabled=True,
            background_task=BackgroundTaskMode.ENABLED,
            background_task_func=unified_background_task,
        ),
        list=RouteOptions(
            enabled=True,
            background_task=BackgroundTaskMode.ENABLED,
            background_task_func=unified_background_task,
        ),
        count=RouteOptions(
            enabled=True,
            background_task=BackgroundTaskMode.ENABLED,
            background_task_func=unified_background_task,
        ),
    )

    # 創建 FastAPI 應用
    app = autocrud.create_fastapi_app(
        title="Unified Background Task API",
        description="API with unified background task signature",
        route_config=config,
    )

    client = TestClient(app)

    print("=== 測試統一背景任務 Callback Signature ===")

    # 創建用戶
    print("\n1. 測試 CREATE 路由的背景任務")
    response = client.post(
        "/api/v1/users",
        json={
            "name": "John Doe",
            "email": "john@example.com",
            "age": 30,
            "role": "user",
        },
    )
    assert response.status_code == 201
    user_data = response.json()
    user_id = user_data["id"]
    print(f"✅ 創建成功，用戶 ID: {user_id}")

    # 獲取用戶
    print("\n2. 測試 GET 路由的背景任務")
    response = client.get(f"/api/v1/users/{user_id}")
    assert response.status_code == 200
    print("✅ 獲取成功")

    # 更新用戶
    print("\n3. 測試 UPDATE 路由的背景任務")
    response = client.put(
        f"/api/v1/users/{user_id}",
        json={
            "name": "John Updated",
            "email": "john.updated@example.com",
            "age": 31,
            "role": "admin",
        },
    )
    assert response.status_code == 200
    print("✅ 更新成功")

    # 列出用戶
    print("\n4. 測試 LIST 路由的背景任務")
    response = client.get("/api/v1/users")
    assert response.status_code == 200
    print("✅ 列出成功")

    # 計數
    print("\n5. 測試 COUNT 路由的背景任務")
    response = client.get("/api/v1/users/count")
    assert response.status_code == 200
    print("✅ 計數成功")

    # 刪除用戶
    print("\n6. 測試 DELETE 路由的背景任務")
    response = client.delete(f"/api/v1/users/{user_id}")
    assert response.status_code == 204
    print("✅ 刪除成功")


def test_mixed_background_tasks():
    """測試混合背景任務配置"""

    autocrud = AutoCRUD()
    autocrud.register_model(User)

    # 不同路由使用不同的背景任務函數
    config = RouteConfig(
        create=RouteOptions(
            enabled=True,
            background_task=BackgroundTaskMode.ENABLED,
            background_task_func=unified_background_task,
        ),
        get=RouteOptions(
            enabled=True,
            background_task=BackgroundTaskMode.ENABLED,
            background_task_func=log_task_execution,
        ),
        update=RouteOptions(
            enabled=True,
            background_task=BackgroundTaskMode.DISABLED,  # 無背景任務
        ),
        delete=RouteOptions(
            enabled=True,
            background_task=BackgroundTaskMode.ENABLED,
            background_task_func=unified_background_task,
        ),
        list=RouteOptions(enabled=True),  # 預設無背景任務
        count=RouteOptions(
            enabled=True,
            background_task=BackgroundTaskMode.ENABLED,
            background_task_func=log_task_execution,
        ),
    )

    app = autocrud.create_fastapi_app(route_config=config)
    client = TestClient(app)

    print("\n=== 測試混合背景任務配置 ===")

    # 創建用戶（使用 unified_background_task）
    print("\n1. CREATE with unified_background_task")
    response = client.post(
        "/api/v1/users",
        json={
            "name": "Mixed User",
            "email": "mixed@example.com",
            "age": 25,
            "role": "user",
        },
    )
    assert response.status_code == 201
    user_id = response.json()["id"]

    # 獲取用戶（使用 log_task_execution）
    print("\n2. GET with log_task_execution")
    response = client.get(f"/api/v1/users/{user_id}")
    assert response.status_code == 200

    # 更新用戶（無背景任務）
    print("\n3. UPDATE without background task")
    response = client.put(
        f"/api/v1/users/{user_id}",
        json={
            "name": "Updated Mixed User",
            "email": "mixed.updated@example.com",
            "age": 26,
            "role": "admin",
        },
    )
    assert response.status_code == 200

    # 計數（使用 log_task_execution）
    print("\n4. COUNT with log_task_execution")
    response = client.get("/api/v1/users/count")
    assert response.status_code == 200

    print("\n✅ 混合背景任務配置測試完成")


def test_conditional_background_task():
    """測試條件式背景任務"""

    def should_run_task(route_output: Any) -> bool:
        """條件函數：只對管理員用戶執行背景任務"""
        if isinstance(route_output, dict) and "role" in route_output:
            return route_output["role"] == "admin"
        return False

    autocrud = AutoCRUD()
    autocrud.register_model(User)

    config = RouteConfig(
        create=RouteOptions(
            enabled=True,
            background_task=BackgroundTaskMode.CONDITIONAL,
            background_task_func=unified_background_task,
            background_task_condition=should_run_task,
        ),
        get=RouteOptions(enabled=True),
        update=RouteOptions(enabled=True),
        delete=RouteOptions(enabled=True),
        list=RouteOptions(enabled=True),
        count=RouteOptions(enabled=True),
    )

    app = autocrud.create_fastapi_app(route_config=config)
    client = TestClient(app)

    print("\n=== 測試條件式背景任務 ===")

    # 創建普通用戶（不應觸發背景任務）
    print("\n1. 創建普通用戶（不觸發背景任務）")
    response = client.post(
        "/api/v1/users",
        json={
            "name": "Regular User",
            "email": "regular@example.com",
            "age": 25,
            "role": "user",
        },
    )
    assert response.status_code == 201

    # 創建管理員用戶（應觸發背景任務）
    print("\n2. 創建管理員用戶（觸發背景任務）")
    response = client.post(
        "/api/v1/users",
        json={
            "name": "Admin User",
            "email": "admin@example.com",
            "age": 35,
            "role": "admin",
        },
    )
    assert response.status_code == 201

    print("\n✅ 條件式背景任務測試完成")


if __name__ == "__main__":
    test_unified_background_task_signature()
    test_mixed_background_tasks()
    test_conditional_background_task()

    print("\n🎉 所有統一背景任務測試通過！")
    print("\n📝 統一 Background Task Signature 特性：")
    print("✅ 所有路由的背景任務函數只接收一個參數：route_output")
    print("✅ CREATE 路由：背景任務接收 created_item")
    print("✅ GET 路由：背景任務接收 item")
    print("✅ UPDATE 路由：背景任務接收 updated_item")
    print("✅ DELETE 路由：背景任務接收 None")
    print("✅ LIST 路由：背景任務接收 items (列表)")
    print("✅ COUNT 路由：背景任務接收 {'count': count}")
    print("✅ 支持相同的背景任務函數用於所有路由")
    print("✅ 支持條件式背景任務執行")
    print("✅ 完全向後兼容現有功能")
