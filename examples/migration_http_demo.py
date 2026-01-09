import json
from fastapi import FastAPI
from fastapi.testclient import TestClient
from msgspec import Struct

from autocrud import AutoCRUD
from autocrud.crud.route_templates.migrate import MigrateRouteTemplate


# 1. 定義資料模型
class User(Struct):
    name: str
    age: int


# 2. 設定 AutoCRUD
# 這裡我們手動加入 MigrateRouteTemplate
crud = AutoCRUD()
crud.add_route_template(MigrateRouteTemplate())
crud.add_model(User)

# 3. 建立 FastAPI 應用
app = FastAPI()
crud.apply(app)

# 4. 建立測試客戶端
client = TestClient(app)


def demo_http_streaming_migration():
    print("=== 開始 HTTP 串流遷移演示 ===")

    # 呼叫遷移測試 API (POST)
    # 使用 stream=True 來處理串流回應
    with client.stream("POST", "/user/migrate/test", json={"query": {}}) as response:
        print(f"回應狀態碼: {response.status_code}")
        print(f"Content-Type: {response.headers.get('content-type')}")

        print("\n--- 接收進度 ---")
        # 逐行讀取 JSONL 回應
        for line in response.iter_lines():
            if line:
                data = json.loads(line)
                # 根據訊息類型顯示不同內容
                if "status" in data:
                    status = data.get("status")
                    msg = data.get("message")
                    err = data.get("error")
                    output = f"[進度] ID: {data.get('resource_id')} | 狀態: {status}"
                    if msg:
                        output += f" | 訊息: {msg}"
                    if err:
                        output += f" | 錯誤: {err}"
                    print(output)
                elif "total" in data:
                    print("\n--- 最終結果 ---")
                    print(f"總計: {data.get('total')}")
                    print(f"成功: {data.get('success')}")
                    print(f"失敗: {data.get('failed')}")
                    print(f"跳過: {data.get('skipped')}")

    print("\n=== 演示結束 ===")


if __name__ == "__main__":
    # 先隨便新增一些資料，讓遷移有東西可以掃描 (雖然版本相同會被 skipped)
    client.post("/user", json={"name": "Alice", "age": 30})
    client.post("/user", json={"name": "Bob", "age": 25})

    demo_http_streaming_migration()
