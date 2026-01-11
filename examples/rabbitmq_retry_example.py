"""
RabbitMQ 重試機制示例

這個示例展示了如何使用 RabbitMQ 消息隊列的重試機制，
包括：
- 自動重試失敗的任務
- 可配置的重試延遲
- 超過最大重試次數後發送到 dead letter queue
"""

from autocrud import ResourceManager
from autocrud.message_queue.rabbitmq import RabbitMQMessageQueue
from autocrud.resource_manager.storage_factory import SimpleStorageFactory
from autocrud.types import Job, Resource
from msgspec import Struct


class ProcessingTask(Struct):
    """示例任務資料結構"""

    task_id: str
    data: str
    should_fail: bool = False
    retry_count: int = 0


async def main():
    # 1. 設定 ResourceManager
    storage_factory = SimpleStorageFactory()
    rm = ResourceManager(
        resource_type=Job[ProcessingTask],
        storage_factory=storage_factory,
    )

    # 2. 定義處理函數
    def process_task(resource: Resource[Job[ProcessingTask]]) -> None:
        """
        處理任務的回調函數

        如果任務失敗，會自動重試（最多 max_retries 次）
        超過重試次數後，任務會被移到 dead letter queue
        """
        job = resource.data
        task = job.payload

        print(f"\n處理任務: {task.task_id}")
        print(f"  數據: {task.data}")
        print(f"  重試次數: {job.retries}")
        if job.errmsg:
            print(f"  上次錯誤: {job.errmsg}")

        if task.should_fail:
            # 模擬任務失敗
            # 這會觸發重試機制
            # 錯誤信息會被記錄到 job.result
            raise Exception(f"任務 {task.task_id} 處理失敗！")

        print("  ✓ 任務成功完成")

    # 3. 創建 RabbitMQ 消息隊列，配置重試參數
    queue = RabbitMQMessageQueue(
        process_task,
        rm,
        amqp_url="amqp://guest:guest@localhost:5672/",
        queue_prefix="my_task:",
        max_retries=3,  # 最多重試 3 次
        retry_delay_seconds=10,  # 每次重試延遲 10 秒
    )

    # 4. 添加一些任務到隊列
    print("添加任務到隊列...")

    # 這個任務會成功
    task1 = ProcessingTask(
        task_id="task-1", data="This will succeed", should_fail=False
    )
    queue.put(task1)

    # 這個任務會失敗並重試
    task2 = ProcessingTask(
        task_id="task-2", data="This will fail and retry", should_fail=True
    )
    queue.put(task2)

    # 5. 開始消費隊列
    # 注意：在實際應用中，這個函數會阻塞
    # 你可能想在單獨的進程或線程中運行它
    print("\n開始消費任務...")
    print("按 Ctrl+C 停止\n")

    try:
        queue.start_consume()
    except KeyboardInterrupt:
        print("\n停止消費")
        queue.stop_consuming()


def demo_queue_structure():
    """
    展示 RabbitMQ 重試機制的隊列結構
    """
    print("""
    RabbitMQ 重試機制架構：
    
    ┌──────────────┐
    │  Main Queue  │ ← 正常任務從這裡消費
    └──────┬───────┘
           │
           │ (任務失敗)
           ↓
    ┌──────────────┐
    │ Retry Queue  │ ← TTL 10秒後自動回到 Main Queue
    └──────┬───────┘
           │
           │ (超過 max_retries)
           ↓
    ┌──────────────┐
    │  Dead Queue  │ ← 永久失敗的任務，不會自動重試
    └──────────────┘
    
    配置參數：
    - max_retries: 最大重試次數（默認 3）
    - retry_delay_seconds: 重試延遲秒數（默認 10）
    
    消息頭：
    - x-retry-count: 當前重試次數
    - x-last-error: 最後一次錯誤信息（截斷到 500 字符）
    """)


if __name__ == "__main__":
    # 顯示架構說明
    demo_queue_structure()

    # 運行示例（需要 RabbitMQ 服務器）
    # asyncio.run(main())

    print("\n注意：此示例需要 RabbitMQ 服務器運行。")
    print("請先啟動 RabbitMQ，然後取消註釋 asyncio.run(main()) 來運行示例。")
