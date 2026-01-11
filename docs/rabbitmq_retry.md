# RabbitMQ 重試機制

## 概述

RabbitMQ 消息隊列現在支持自動重試機制，當消息處理失敗時會自動重試，並在超過最大重試次數後將消息發送到 dead letter queue。

**注意**：SimpleMessageQueue 也支持錯誤信息記錄功能，會自動將錯誤信息寫入 Job 的 `errmsg` 字段並遞增 `retries` 計數器。

## 功能特性

- ✅ **自動重試**：失敗的任務會自動重新入隊並延遲執行
- ✅ **可配置延遲**：可設定重試延遲時間（默認 10 秒）
- ✅ **最大重試次數**：可設定最大重試次數（默認 3 次）
- ✅ **Dead Letter Queue**：超過重試次數的任務會進入 dead queue，不會再自動重試
- ✅ **錯誤追蹤**：每個消息會記錄重試次數和最後的錯誤信息
- ✅ **Revision-based 錯誤記錄**：利用 AutoCRUD 的版本管理系統，每次重試時錯誤信息會更新到 Job 的 `result` 字段，歷史錯誤會保留在舊的 revision 中

## 快速開始

### 基本使用

```python
from autocrud.message_queue.rabbitmq import RabbitMQMessageQueue
from autocrud import ResourceManager

# 創建隊列，配置重試參數
queue = RabbitMQMessageQueue(
    resource_manager=rm,
    queue_name="my_queue",
    max_retries=3,              # 最多重試 3 次
    retry_delay_seconds=10,     # 每次重試延遲 10 秒
)

# 定義處理函數
def process_message(resource):
    # 如果拋出異常，消息會自動重試
    if some_error_condition:
        raise Exception("處理失敗")
    
    # 成功處理
    print("處理成功")

# 開始消費
queue.start_consume(process_message)
```

### 自定義重試配置

```python
# 更長的重試延遲和更多重試次數
queue = RabbitMQMessageQueue(
    resource_manager=rm,
    queue_name="important_queue",
    max_retries=5,              # 重試 5 次
    retry_delay_seconds=30,     # 每次延遲 30 秒
)
```

## 工作原理

### 隊列結構

系統會自動創建三個隊列：

1. **主隊列** (`{queue_name}`)
   - 所有新任務首先進入這裡
   - 消費者從這裡獲取任務

2. **重試隊列** (`{queue_name}_retry`)
   - 失敗的任務被發送到這裡
   - 配置了 TTL (Time-To-Live)
   - TTL 到期後自動回到主隊列

3. **死信隊列** (`{queue_name}_dead`)
   - 超過最大重試次數的任務進入這裡
   - 不會自動重試
   - 需要手動處理或檢查

### 重試流程

```
任務入隊 → 主隊列
              ↓
          處理成功? ─Yes→ 完成
              ↓ No
          重試次數 < max_retries?
              ↓ Yes
          重試隊列 (等待 retry_delay_seconds)
              ↓
          回到主隊列
              ↓ No
          死信隊列 (不再重試)
```

### 消息頭資訊

每個重試的消息會包含以下頭資訊：

- `x-retry-count`: 當前重試次數（從 1 開始）
- `x-last-error`: 最後一次失敗的錯誤信息（截斷到 500 字符）

### Job 錯誤記錄

每次任務失敗時，Job 資源會被更新：

- `job.result`: 儲存完整的錯誤信息（不截斷）
- `job.retries`: 記錄當前的重試次數
- `job.status`: 設置為 `FAILED`

由於 AutoCRUD 使用 revision-based 的資源管理系統，每次更新會創建新的 revision。這意味著：

1. **最新的錯誤**：`job.errmsg` 總是包含最新的錯誤信息
2. **歷史追蹤**：可以通過查看舊的 revision 來查看之前的錯誤
3. **無需額外存儲**：不需要維護錯誤歷史列表，revision 系統自動處理

```python
# 獲取 Job 的所有 revision 來查看錯誤歷史
history = resource_manager.list_revisions(job_resource_id)
for rev in history:
    job = resource_manager.get(job_resource_id, revision_id=rev.revision_id)
    print(f"Retry {job.data.retries}: {job.data.errmsg}")
```

## 配置參數

| 參數 | 類型 | 默認值 | 說明 |
|------|------|--------|------|
| `max_retries` | int | 3 | 最大重試次數 |
| `retry_delay_seconds` | int | 10 | 重試延遲秒數 |
| `queue_name` | str | "autocrud_jobs" | 主隊列名稱 |

## 錯誤處理

### 回調函數錯誤

當處理函數拋出異常時：
- 任務會被標記為失敗
- 如果重試次數 < max_retries，發送到重試隊列
- 如果重試次數 >= max_retries，發送到死信隊列

```python
def process_task(resource):
    try:
        # 處理邏輯
        do_something(resource.data)
    except SpecificError:
        # 可以選擇重新拋出讓系統重試
        raise
    except FatalError:
        # 或者捕獲並處理，不重試
        log_error("致命錯誤，不重試")
```

### 系統錯誤

對於系統級錯誤（如資源無法獲取），系統也會應用相同的重試機制。

## 監控和除錯

### 查看隊列狀態

使用 RabbitMQ 管理介面查看：
- 主隊列的消息數量
- 重試隊列的消息數量（正在等待重試的任務）
- 死信隊列的消息數量（失敗的任務）

### 處理死信隊列

死信隊列中的消息需要手動處理：

```python
# 連接到死信隊列
dead_queue = RabbitMQMessageQueue(
    resource_manager=rm,
    queue_name=f"{original_queue_name}_dead",
)

# 手動處理或記錄
def handle_dead_message(resource):
    # 記錄到日誌
    log.error(f"Dead letter: {resource.data}")
    
    # 或者嘗試手動修復後重新處理
    if can_fix(resource.data):
        original_queue.put(resource.data.payload)
```

## 最佳實踐

1. **設置適當的重試次數**
   - 太少可能導致偶發錯誤無法恢復
   - 太多會延遲發現真正的問題

2. **合理配置延遲時間**
   - 考慮下游服務的恢復時間
   - 避免過於頻繁的重試造成系統壓力

3. **監控死信隊列**
   - 定期檢查死信隊列
   - 分析失敗原因並改進系統

4. **冪等性設計**
   - 確保重試不會造成副作用
   - 處理函數應該是冪等的

## 完整示例

查看 `examples/rabbitmq_retry_example.py` 獲取完整的使用示例。

## 測試

所有消息隊列的測試都整合在 `tests/test_message_queue.py` 中：

### 統一測試 (TestMessageQueueUnified)
這些測試同時針對 SimpleMessageQueue 和 RabbitMQ，確保兩種實現的外部行為一致：
- ✅ 基本工作流程（put, pop, complete, fail）
- ✅ 錯誤信息記錄到 Job
- ✅ 重試計數器遞增
- ✅ 消費循環中的錯誤處理

### RabbitMQ 專屬測試 (TestRabbitMQRetryMechanism)
這些測試只針對 RabbitMQ 的重試機制：
- ✅ 自動重試隊列
- ✅ Dead letter queue
- ✅ 重試次數限制
- ✅ 消息頭錯誤信息截斷

運行測試：
```bash
# 運行所有消息隊列測試
uv run pytest tests/test_message_queue.py -v

# 只運行統一測試
uv run pytest tests/test_message_queue.py::TestMessageQueueUnified -v

# 只運行 RabbitMQ 重試測試
uv run pytest tests/test_message_queue.py::TestRabbitMQRetryMechanism -v

# 完整測試套件
make test
```

## 注意事項

- 需要 RabbitMQ 服務器運行
- 確保安裝了 `pika` 套件
- 重試機制適用於所有類型的錯誤，包括系統錯誤和業務邏輯錯誤
