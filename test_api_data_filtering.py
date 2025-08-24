#!/usr/bin/env python3
"""
測試 ListRouteTemplate 的 data filtering 功能
驗證 API 端點可以正確處理 data_conditions 參數
"""

from dataclasses import dataclass
import json
import urllib.parse
from fastapi.testclient import TestClient
from fastapi import FastAPI
from autocrud.crud.core import AutoCRUD, MemoryStorageFactory


@dataclass
class User:
    name: str
    age: int
    department: str
    email: str


def test_api_data_filtering():
    """測試 API 端點的 data filtering 功能"""

    # 創建 AutoCRUD 實例
    storage_factory = MemoryStorageFactory()
    autocrud = AutoCRUD()

    # 註冊 User 模型並設置索引欄位
    autocrud.add_model(
        User,
        storage_factory=storage_factory,
        indexed_fields=[("department", str), ("age", int), ("email", str)],
    )

    # 創建 FastAPI 應用並添加路由
    app = FastAPI()
    autocrud.apply(app)

    # 創建測試客戶端
    client = TestClient(app)

    # 檢查可用路由
    print("Available routes:")
    for route in app.routes:
        print(f"  {route.methods if hasattr(route, 'methods') else 'N/A'} {route.path}")

    # 創建測試數據
    users_data = [
        {
            "name": "Alice",
            "age": 25,
            "department": "Engineering",
            "email": "alice@example.com",
        },
        {
            "name": "Bob",
            "age": 30,
            "department": "Marketing",
            "email": "bob@example.com",
        },
        {
            "name": "Charlie",
            "age": 35,
            "department": "Engineering",
            "email": "charlie@example.com",
        },
        {
            "name": "Diana",
            "age": 28,
            "department": "Sales",
            "email": "diana@example.com",
        },
    ]

    # 創建用戶
    created_users = []
    for user_data in users_data:
        response = client.post("/user", json=user_data)
        print(f"Create user response: {response.status_code}, {response.text}")
        assert response.status_code == 200
        created_users.append(response.json())

    print("✅ 創建了 4 個測試用戶")

    # 先檢查所有用戶是否都存在
    response = client.get("/user/data")
    all_users = response.json()
    print(f"Total users created: {len(all_users)}")
    for user in all_users:
        print(f"  User: {user}")

    # 先測試沒有過濾條件的查詢
    response = client.get("/user/data")
    print(f"No filter response: {len(response.json())} users")

    # 測試限制數量的查詢
    response = client.get("/user/data?limit=2")
    print(f"Limit 2 response: {len(response.json())} users")

    # 測試 1: 按部門過濾（Engineering）
    data_conditions = json.dumps(
        [{"field_path": "department", "operator": "eq", "value": "Engineering"}]
    )
    encoded_conditions = urllib.parse.quote(data_conditions)

    response = client.get(f"/user/data?data_conditions={encoded_conditions}")
    print(f"Data conditions: {data_conditions}")
    print(f"Encoded conditions: {encoded_conditions}")
    print(f"Response status: {response.status_code}")
    print(f"Response content: {response.text}")
    if response.status_code != 200:
        print("Error details:", response.json())
    assert response.status_code == 200

    engineering_users = response.json()
    assert len(engineering_users) == 2
    assert all(user["department"] == "Engineering" for user in engineering_users)
    print("✅ 測試 1: 按部門過濾 - 通過")

    # 測試 2: 按年齡範圍過濾（age > 25）
    data_conditions = json.dumps([{"field_path": "age", "operator": "gt", "value": 25}])

    response = client.get(f"/user/data?data_conditions={data_conditions}")
    assert response.status_code == 200

    older_users = response.json()
    assert len(older_users) == 3  # Bob(30), Charlie(35), Diana(28)
    assert all(user["age"] > 25 for user in older_users)
    print("✅ 測試 2: 按年齡過濾 - 通過")

    # 測試 3: 組合條件（Engineering 且 age >= 30）
    data_conditions = json.dumps(
        [
            {"field_path": "department", "operator": "eq", "value": "Engineering"},
            {"field_path": "age", "operator": "gte", "value": 30},
        ]
    )

    response = client.get(f"/user/data?data_conditions={data_conditions}")
    assert response.status_code == 200

    filtered_users = response.json()
    assert len(filtered_users) == 1  # 只有 Charlie
    assert filtered_users[0]["name"] == "Charlie"
    print("✅ 測試 3: 組合條件過濾 - 通過")

    # 測試 4: 測試 /meta 端點
    data_conditions = json.dumps(
        [{"field_path": "department", "operator": "eq", "value": "Marketing"}]
    )

    response = client.get(f"/user/meta?data_conditions={data_conditions}")
    print(f"Meta endpoint response status: {response.status_code}")
    if response.status_code != 200:
        print(f"Meta endpoint error: {response.content}")
    assert response.status_code == 200

    meta_data = response.json()
    assert len(meta_data) == 1  # 只有 Bob
    print("✅ 測試 4: /meta 端點 data filtering - 通過")

    # 測試 5: 測試 /full 端點
    data_conditions = json.dumps(
        [{"field_path": "email", "operator": "contains", "value": "@example.com"}]
    )

    response = client.get(f"/user/full?data_conditions={data_conditions}")
    assert response.status_code == 200

    full_data = response.json()
    assert len(full_data) == 4  # 所有用戶都符合條件
    assert all("@example.com" in item["data"]["email"] for item in full_data)
    print("✅ 測試 5: /full 端點 data filtering - 通過")

    # 測試 6: 測試無效的 JSON 格式
    response = client.get("/user/data?data_conditions=invalid_json")
    assert response.status_code == 400
    assert "Invalid data_conditions format" in response.json()["detail"]
    print("✅ 測試 6: 無效 JSON 格式錯誤處理 - 通過")

    # 測試 7: 測試無效的操作符
    data_conditions = json.dumps(
        [{"field_path": "age", "operator": "invalid_operator", "value": 25}]
    )

    response = client.get(f"/user/data?data_conditions={data_conditions}")
    assert response.status_code == 400
    print("✅ 測試 7: 無效操作符錯誤處理 - 通過")

    print("\n🎉 所有 API data filtering 測試都通過了！")


if __name__ == "__main__":
    test_api_data_filtering()
