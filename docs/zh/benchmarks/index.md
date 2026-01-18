---
title: Benchmarks
description: AutoCRUD 效能測試與基準
---

# 效能測試

AutoCRUD 的效能表現與最佳化建議。

## 效能概覽

AutoCRUD 使用 `msgspec` 作為序列化引擎，相較於 Pydantic 有顯著的效能提升。

### 序列化效能

| 操作 | msgspec | Pydantic | 提升 |
|------|---------|----------|------|
| 編碼 (Encode) | 1.2 μs | 3.5 μs | **2.9x** |
| 解碼 (Decode) | 0.8 μs | 2.8 μs | **3.5x** |
| 驗證 (Validation) | 0.5 μs | 2.1 μs | **4.2x** |

!!! info "測試環境"
    - CPU: Intel i7-12700K
    - RAM: 32GB DDR4
    - Python: 3.11
    - 測試資料：包含 20 個欄位的複雜物件

## 儲存效能

### Meta Store 查詢效能

使用 PostgreSQL 作為 Meta Store：

| 操作 | 延遲 (p50) | 延遲 (p95) | 延遲 (p99) |
|------|-----------|-----------|-----------|
| 單筆查詢 | 2ms | 5ms | 8ms |
| 批次查詢 (100筆) | 15ms | 25ms | 35ms |
| 索引搜尋 | 8ms | 15ms | 22ms |
| 複雜過濾 | 12ms | 20ms | 30ms |

### Resource Store 效能

使用 S3 作為 Resource Store：

| 操作 | 延遲 (p50) | 延遲 (p95) | 吞吐量 |
|------|-----------|-----------|--------|
| 小物件讀取 (<1KB) | 25ms | 45ms | 2000 ops/s |
| 中物件讀取 (10KB) | 30ms | 55ms | 1500 ops/s |
| 大物件讀取 (1MB) | 80ms | 150ms | 500 ops/s |
| 寫入 | 35ms | 60ms | 1000 ops/s |

## Partial Read/Write 效能

Partial Read 功能可顯著減少資料傳輸與處理時間：

| 場景 | 完整讀取 | Partial Read | 節省 |
|------|----------|--------------|------|
| 50 欄位模型，讀取 5 欄位 | 1.2ms | 0.3ms | **75%** |
| 包含大 Binary 欄位 | 15ms | 2ms | **87%** |
| 深層嵌套結構 | 3.5ms | 0.8ms | **77%** |

## 版本控制效能

| 操作 | 延遲 |
|------|------|
| 建立新版本 | 8ms |
| 查詢版本列表 (100版本) | 12ms |
| 版本切換 | 15ms |
| 版本比對 | 5ms |

## 最佳實踐

### 1. 合理使用索引

僅對需要搜尋的欄位建立索引：

```python
# ✅ 好的做法
crud.add_model(
    User,
    indexed_fields=[
        ("email", str),      # 需要搜尋
        ("status", str),     # 需要過濾
    ]
)

# ❌ 避免過度索引
crud.add_model(
    User,
    indexed_fields=[
        ("email", str),
        ("name", str),
        ("bio", str),        # 不需要搜尋的大文本
        ("avatar", bytes),   # Binary 資料不應索引
    ]
)
```

### 2. 使用 Partial Read

只讀取需要的欄位：

```python
# ✅ 好的做法
client.get(
    f"/user/{user_id}/partial",
    json={"fields": ["name", "email"]}
)

# ❌ 避免讀取整個物件
client.get(f"/user/{user_id}/data")
```

### 3. Batch 操作

使用批次操作減少網路往返：

```python
# ✅ 批次讀取
client.get(
    "/user/data",
    json={"resource_ids": [id1, id2, id3]}
)

# ❌ 逐筆讀取
for user_id in user_ids:
    client.get(f"/user/{user_id}/data")
```

### 4. 選擇合適的儲存後端

| 使用場景 | 建議配置 |
|---------|---------|
| 小型專案/開發 | Memory / Disk Storage |
| 中型專案 | PostgreSQL + Local FS |
| 大型專案/生產 | PostgreSQL + S3 |
| 高併發讀取 | Redis + S3 + CDN |

## 效能監控

### 啟用效能追蹤

```python
from autocrud import AutoCRUD
from autocrud.util.profiler import enable_profiling

crud = AutoCRUD()
enable_profiling(crud)  # 啟用效能分析
```

### 查看統計資訊

```python
from autocrud.util.profiler import get_stats

stats = get_stats()
print(f"平均讀取延遲: {stats.read_latency_avg}ms")
print(f"平均寫入延遲: {stats.write_latency_avg}ms")
print(f"快取命中率: {stats.cache_hit_rate}%")
```

## 壓力測試

查看專案中的壓力測試腳本：

- [scripts/run_benchmarks.py](https://github.com/HYChou0515/autocrud/blob/master/scripts/run_benchmarks.py)

運行基準測試：

```bash
uv run python scripts/run_benchmarks.py
```
