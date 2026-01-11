# Message Queue Integration in ResourceManager

## 概述

Message queue 已經完全整合到 `ResourceManager` 中,就像 `blob_store` 一樣。當 resource 是 `Job` 子類別時,`ResourceManager` 會自動擁有 message queue 的能力。

## 核心變更

### 1. IResourceManager 介面新增方法

```python
class IResourceManager(ABC, Generic[T]):
    @abstractmethod
    def get_message_queue(self) -> IMessageQueue[T] | None:
        """Get the message queue for this resource manager if available."""
        ...

    @abstractmethod
    def has_message_queue(self) -> bool:
        """Check if this resource manager has a message queue."""
        ...
```

### 2. ResourceManager 實作

```python
class ResourceManager(IResourceManager[T], Generic[T]):
    def __init__(
        self,
        resource_type: type[T],
        *,
        storage: IStorage,
        blob_store: IBlobStore | None = None,
        message_queue: IMessageQueue | None = None,  # 新增
        ...
    ):
        self.blob_store = blob_store
        self.message_queue = message_queue  # 儲存 message queue
        ...
    
    def get_message_queue(self):
        """Get the message queue for this resource manager if available."""
        return self.message_queue
    
    def has_message_queue(self) -> bool:
        """Check if this resource manager has a message queue."""
        return self.message_queue is not None
```

## 使用方式

### 方法一: 透過 ResourceManager 取得 (推薦)

```python
from autocrud import AutoCRUD
from autocrud.types import Job
from msgspec import Struct

class EmailPayload(Struct):
    to: str
    subject: str
    body: str

class EmailJob(Job[EmailPayload]):
    pass

# 建立 AutoCRUD
crud = AutoCRUD()
crud.add_model(EmailJob, indexed_fields=[("status", str)])

# 透過 ResourceManager 取得 message queue
rm = crud.get_resource_manager(EmailJob)
if rm.has_message_queue():
    mq = rm.get_message_queue()
    
    # 使用 message queue
    with rm.meta_provide(user="worker"):
        job = mq.put(EmailPayload(to="user@example.com", ...))
        next_job = mq.pop()
        if next_job:
            mq.complete(next_job.info.resource_id, result="Done")
```

### 方法二: 透過 AutoCRUD 取得 (向後相容)

```python
# 也可以從 AutoCRUD 直接取得 (向後相容)
mq = crud.get_message_queue(EmailJob)

# 兩種方式取得的是同一個 message queue 實例
assert crud.get_message_queue(EmailJob) is rm.get_message_queue()
```

## 設計理念

### 類似 blob_store 的模式

就像 `blob_store` 一樣:
- **有需要才有**: 只有 `Job` 子類別才會有 message queue
- **統一介面**: 透過 `ResourceManager` 統一存取
- **自動偵測**: AutoCRUD 自動判斷是否需要建立 message queue
- **可選功能**: 可以明確停用 (`message_queue_factory=None`)

### blob_store vs message_queue 對照

| 特性 | blob_store | message_queue |
|------|-----------|---------------|
| **觸發條件** | 資料包含 `Binary` 類型 | model 是 `Job` 子類別 |
| **存取方法** | `rm.get_blob(file_id)` | `rm.get_message_queue()` |
| **檢查方法** | `rm.blob_store is not None` | `rm.has_message_queue()` |
| **設定方式** | 透過 `AutoCRUD(blob_store=...)` | 透過 `AutoCRUD(message_queue_factory=...)` |
| **目的** | 優化大型二進位資料儲存 | 提供非同步任務佇列功能 |

## 範例

完整範例請參考:
- [examples/resource_manager_mq_example.py](../examples/resource_manager_mq_example.py)

測試範例請參考:
- [tests/test_resource_manager_mq.py](../tests/test_resource_manager_mq.py)
- [tests/test_autocrud_mq_integration.py](../tests/test_autocrud_mq_integration.py)

## 優點

1. **一致性**: 與 blob_store 使用相同的設計模式
2. **便利性**: 直接從 ResourceManager 存取,不需要額外查找
3. **類型安全**: TypeScript-style 的類型檢查
4. **向後相容**: 原有的 `AutoCRUD.get_message_queue()` 仍然可用
5. **自動化**: 自動偵測並建立,無需手動配置
