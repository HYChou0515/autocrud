---
title: S3 + SQLite 鎖定機制
description: 基於 ETag 的樂觀鎖機制，防止多實例寫入衝突
---

# S3 + SQLite 鎖定機制

## 概述

S3SqliteMetaStore 實作了基於 **ETag 的樂觀鎖（Optimistic Locking）** 機制，用於防止多個實例同時寫入造成的資料衝突。

!!! info "New in version 0.7.6"

## 🔐 工作原理

### ETag（Entity Tag）

ETag 是 S3 物件的版本識別碼，每次物件被修改時，S3 會自動產生新的 ETag。我們可以利用這個特性來檢測檔案是否被其他程序修改。

### 樂觀鎖流程

1. **下載時記錄 ETag**：從 S3 下載資料庫檔案時，記錄當前的 ETag
2. **本地操作**：在本地 SQLite 資料庫上執行所有操作
3. **同步前檢查**：上傳前先檢查 S3 上的 ETag 是否與本地記錄的一致
4. **衝突處理**：
   - 如果 ETag 匹配 → 允許上傳，更新本地 ETag
   - 如果 ETag 不匹配 → 拋出 `S3ConflictError` 異常

```
Instance A                  S3                      Instance B
    |                       |                           |
    |--- download (ETag:1)--|                           |
    |                       |                           |
    |                       |                           |--- download (ETag:1)
    |                       |                           |
    | (modify locally)      |                           |
    |                       |                           |
    |--- check ETag:1? ---> |                           |
    |<--- yes (ETag:1) ----- |                           |
    |--- upload ----------> |                           |
    |                       |--- new ETag:2             |
    |                       |                           |
    |                       |                           | (modify locally)
    |                       |                           |
    |                       |                           |--- check ETag:1? --->
    |                       | <--- no! (ETag:2) --------|
    |                       |                           |--- CONFLICT! ❌
```

## 💻 使用方式

### 基本用法（啟用鎖定）

```python
from autocrud.resource_manager.meta_store.sqlite3 import (
    S3SqliteMetaStore,
    S3ConflictError,
)

# 建立 store（預設啟用鎖定）
store = S3SqliteMetaStore(
    bucket="my-bucket",
    key="metadata/my-db.db",
    enable_locking=True,  # 預設為 True
)

# 新增資料
store["resource-1"] = meta

# 同步到 S3
try:
    store.sync_to_s3()
except S3ConflictError as e:
    print(f"衝突: {e}")
    # 處理衝突...
```

### 禁用鎖定

如果你確定只有單一實例寫入，可以禁用鎖定以提升性能：

```python
store = S3SqliteMetaStore(
    bucket="my-bucket",
    key="metadata/my-db.db",
    enable_locking=False,  # 禁用鎖定
)
```

### 🔄 自動重新載入

當偵測到衝突時，可以選擇自動從 S3 重新載入資料庫：

```python
store = S3SqliteMetaStore(
    bucket="my-bucket",
    key="metadata/my-db.db",
    enable_locking=True,
    auto_reload_on_conflict=True,  # 衝突時自動重新載入
)

# 當發生衝突時，會自動重新載入並拋出異常
# 本地未同步的變更會被捨棄
try:
    store.sync_to_s3()
except S3ConflictError as e:
    print("已從 S3 重新載入，本地變更已捨棄")
    # 資料庫已經是最新版本，可以重新執行操作
```

### 手動重新載入

```python
# 檢查是否需要同步
if store.is_sync_needed():
    print("S3 上的文件已被修改")
    
    # 手動重新載入
    store.reload_from_s3()
    print("已重新載入最新版本")
```

### 強制同步（繞過檢查）

在某些情況下，你可能需要強制覆蓋 S3 上的版本：

```python
# 強制同步，忽略 ETag 檢查
store.sync_to_s3(force=True)
```

**⚠️ 警告**: 使用 `force=True` 可能會覆蓋其他實例的更改，導致數據丟失。

## 📚 API 參考

### 初始化參數

| 參數 | 類型 | 預設值 | 說明 |
|------|------|--------|------|
| `enable_locking` | `bool` | `True` | 啟用 ETag 樂觀鎖 |
| `auto_reload_on_conflict` | `bool` | `False` | 衝突時自動重新載入 |

### 方法

#### `sync_to_s3(force: bool = False)`

同步本地資料庫到 S3。

- `force`: 強制同步，繞過 ETag 檢查
- **拋出**: `S3ConflictError` 如果偵測到衝突

#### `reload_from_s3()`

從 S3 重新載入資料庫，捨棄本地未同步的變更。

#### `get_current_etag() -> str | None`

獲取本地數據庫副本的當前 ETag。

#### `check_s3_etag() -> str | None`

檢查 S3 上的當前 ETag（不下載檔案）。

#### `is_sync_needed() -> bool`

檢查本地資料庫與 S3 版本是否不同。

## 🔧 衝突處理策略

### 策略 1: 重新載入並重試（推薦）

```python
def safe_update(store, resource_id, new_data):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # 執行更新
            store[resource_id] = new_data
            store.sync_to_s3()
            return True
        except S3ConflictError:
            if attempt < max_retries - 1:
                # 重新載入並重試
                store.reload_from_s3()
                continue
            else:
                # 達到最大重試次數
                raise
    return False
```

### 策略 2: 合併衝突

```python
def merge_update(store, resource_id, update_func):
    try:
        # 嘗試更新
        current = store[resource_id]
        updated = update_func(current)
        store[resource_id] = updated
        store.sync_to_s3()
    except S3ConflictError:
        # 重新載入
        store.reload_from_s3()
        
        # 重新獲取最新資料並套用更新
        current = store[resource_id]
        updated = update_func(current)
        store[resource_id] = updated
        
        # 再次嘗試同步
        store.sync_to_s3()
```

### 策略 3: 使用自動重新載入

```python
store = S3SqliteMetaStore(
    bucket="my-bucket",
    key="metadata/my-db.db",
    auto_reload_on_conflict=True,
)

# 第一次嘗試
try:
    store[resource_id] = new_data
    store.sync_to_s3()
except S3ConflictError:
    # 已自動重新載入，重新執行操作
    store[resource_id] = new_data
    store.sync_to_s3()
```

## ✅ 最佳實踐

### 推薦做法

1. **單寫入者模式**：盡可能只讓一個實例負責寫入
2. **批次操作**：累積多個變更後一次性同步
3. **重試機制**：實作衝突重試邏輯
4. **監控**：記錄衝突發生頻率

```python
# 批次操作範例
store = S3SqliteMetaStore(
    bucket="my-bucket",
    key="metadata/my-db.db",
    auto_sync=False,  # 停用自動同步
)

# 批次更新
for resource in resources:
    store[resource.id] = resource

# 一次性同步
try:
    store.sync_to_s3()
except S3ConflictError:
    # 處理衝突...
```

### 避免做法

1. **頻繁同步**：不要每次操作都同步
2. **停用鎖定**：除非確定單實例，否則不要停用
3. **忽略衝突**：不要捕獲異常後不處理
4. **濫用 force**：不要隨意使用強制同步

## ⚡ 效能考量

### ETag 檢查開銷

- ETag 檢查只需要一次 `head_object` API 調用（輕量級）
- 相比數據丟失風險，開銷可以忽略

### 優化建議

1. **調整同步間隔**：增大 `sync_interval` 減少同步頻率
2. **停用自動同步**：手動控制同步時機
3. **批次操作**：減少同步次數

```python
store = S3SqliteMetaStore(
    bucket="my-bucket",
    key="metadata/my-db.db",
    auto_sync=True,
    sync_interval=100,  # 每 100 次操作同步一次
)
```

## 🚨 異常處理

### S3ConflictError

當偵測到 ETag 衝突時拋出此異常。

```python
from autocrud.resource_manager.meta_store.sqlite3 import S3ConflictError

try:
    store.sync_to_s3()
except S3ConflictError as e:
    print(f"衝突詳情: {e}")
    # 異常訊息包含：
    # - 期望的 ETag
    # - 當前 S3 上的 ETag
    # - 是否已重新載入
```

## 🌍 多區域部署

對於多區域部署，建議：

1. **讀寫分離**：指定特定區域為寫入區域
2. **定期同步**：定時從主區域拉取最新資料
3. **衝突解決**：實作應用層面的衝突解決策略

```python
# 主區域（可寫）
primary_store = S3SqliteMetaStore(
    bucket="primary-bucket",
    key="metadata/my-db.db",
    region_name="us-east-1",
    enable_locking=True,
)

# 副本區域（只讀）
replica_store = S3SqliteMetaStore(
    bucket="replica-bucket",
    key="metadata/my-db.db",
    region_name="ap-northeast-1",
    enable_locking=False,  # 只讀，禁用鎖定
)

# 定期同步
def sync_replica():
    replica_store.reload_from_s3()
```

## 🧪 測試

完整的測試範例請參考：

:octicons-mark-github-16: [tests/test_s3_meta_store_locking.py](https://github.com/HYChou0515/autocrud/blob/master/tests/test_s3_meta_store_locking.py)

```bash
# 執行鎖定機制測試
uv run pytest tests/test_s3_meta_store_locking.py -v
```
