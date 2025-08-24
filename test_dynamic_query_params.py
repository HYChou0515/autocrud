#!/usr/bin/env python3
"""
測試動態查詢參數功能
驗證 API 端點可以接受基於 indexed_fields 的動態參數
"""

from dataclasses import dataclass
import json
import urllib.parse
from fastapi.testclient import TestClient
from fastapi import FastAPI

from autocrud import AutoCRUD
from autocrud.resource_manager.core import ResourceType, IndexableField


@dataclass
class User:
    name: str
    age: int
    department: str
    is_active: bool
    salary: float


def test_dynamic_query_params():
    """測試動態查詢參數功能"""
    
    # 創建 FastAPI app
    app = FastAPI()
    
    # 定義資源類型，包含 indexed_fields
    user_type = ResourceType(
        name="user",
        schema=User,
        indexed_fields=[
            IndexableField(field_path="name", field_type=str),
            IndexableField(field_path="age", field_type=int), 
            IndexableField(field_path="department", field_type=str),
            IndexableField(field_path="is_active", field_type=bool),
            IndexableField(field_path="salary", field_type=float),
        ]
    )
    
    # 創建 AutoCRUD 實例
    autocrud = AutoCRUD(
        resource_types=[user_type],
        meta_store_config={"type": "simple"},
        resource_store_config={"type": "simple"}
    )
    
    # 應用到 FastAPI
    autocrud.apply(app)
    
    # 創建測試用戶端
    client = TestClient(app)
    
    # 創建一些測試資料
    test_users = [
        User(name="Alice", age=30, department="Engineering", is_active=True, salary=75000.0),
        User(name="Bob", age=25, department="Marketing", is_active=True, salary=60000.0),
        User(name="Charlie", age=35, department="Engineering", is_active=False, salary=80000.0),
        User(name="Diana", age=28, department="Sales", is_active=True, salary=65000.0),
    ]
    
    # 插入測試資料
    for user in test_users:
        response = client.post("/user", json=user.__dict__)
        assert response.status_code == 200
    
    # 測試 1: 字串欄位等值查詢
    response = client.get("/user/data?department=Engineering")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all(user["department"] == "Engineering" for user in data)
    
    # 測試 2: 字串欄位包含查詢
    response = client.get("/user/data?name__contains=a")
    assert response.status_code == 200
    data = response.json()
    # Alice, Diana, Charlie 都包含 'a' 或 'A'（忽略大小寫）
    assert len(data) >= 1
    
    # 測試 3: 數字欄位大於查詢
    response = client.get("/user/data?age__gt=30")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1  # 只有 Charlie (35)
    assert data[0]["age"] > 30
    
    # 測試 4: 數字欄位範圍查詢
    response = client.get("/user/data?age__gte=25&age__lt=35")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3  # Alice (30), Bob (25), Diana (28)
    assert all(25 <= user["age"] < 35 for user in data)
    
    # 測試 5: 布爾欄位查詢
    response = client.get("/user/data?is_active=true")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3  # Alice, Bob, Diana
    assert all(user["is_active"] is True for user in data)
    
    # 測試 6: 浮點數欄位查詢
    response = client.get("/user/data?salary__gte=70000")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2  # Alice (75000), Charlie (80000)
    assert all(user["salary"] >= 70000 for user in data)
    
    # 測試 7: 組合查詢（動態參數 + 傳統 JSON）
    json_conditions = json.dumps([
        {"field_path": "department", "operator": "eq", "value": "Engineering"}
    ])
    response = client.get(f"/user/data?data_conditions={urllib.parse.quote(json_conditions)}&is_active=true")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1  # 只有 Alice
    assert data[0]["department"] == "Engineering"
    assert data[0]["is_active"] is True
    
    # 測試 8: 多個動態參數組合
    response = client.get("/user/data?department=Engineering&age__gte=30&is_active=true")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1  # 只有 Alice
    assert data[0]["name"] == "Alice"
    
    # 測試 9: 不等於操作符
    response = client.get("/user/data?department__ne=Engineering")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2  # Bob (Marketing), Diana (Sales)
    assert all(user["department"] != "Engineering" for user in data)
    
    print("所有動態查詢參數測試通過！")


if __name__ == "__main__":
    test_dynamic_query_params()
