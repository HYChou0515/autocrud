# Quickstart - Job Queue

在這個文件中，我們會介紹如何使用 autocrud 快速建置一個完整的 job 管理機制與 queue 系統。

說到 job queue，普遍會聯想到的包含 `celery`、基於 celery 的 `flower`，或是原生的 RabbitMQ 及其 client package `pika`。這些工具本身都提供了強大的底層能力，但在實務上，若要直接使用來支撐一個「可操作、可觀測、可管理」的 job 系統，通常仍需要額外投入不少工程工作。

常見會遇到的問題包含：

- job handler 管理與易於上手、不易踩雷的設定方式
- queue 中目前有哪些 job 尚未被處理
- job fail 後的 retry 機制與策略
- 每個 job 的 logs 如何收集、查詢與下載
- job rerun 的可能性，以及是否保留 job 執行前的狀態
- 無法以「job」為單位進行統一管理（多半只看到 task 或 message）
- 缺乏對系統管理者友善的操作介面（需依賴 CLI、broker 工具或分散的 log）
- backend（celery / rabbitmq）細節暴露過多，導致學習成本高且容易誤用

換句話說，現有工具大多專注在「任務的傳遞與執行」，但對於「任務的管理與操作體驗」著墨較少。

autocrud 在這一層之上提供了一個更高階的抽象，讓開發者可以用一致的方式定義與提交 job，同時也提供完整的 job metadata 管理、log 管理、retry / rerun 機制，以及對系統管理者友善的 Web 操作介面。

透過 autocrud，你可以：

- 以最小設定建立 job queue（支援 celery / rabbitmq backend）
- 將每個 job 視為一級資源進行管理（status、input、log、歷史紀錄）
- 直接在 Web UI 中查看所有 job、細節與執行狀態
- 為每個 job 提供獨立的 log 紀錄與下載能力
- 支援 retry 與 rerun，並保留 execution lineage

接著我們會一步一步帶你建立一個完整可用的 job queue 系統。

## 1. 定義 job schema 與 job handler

首先，我們先定義這個 job 的輸入（`Payload`）以及對應的 job type。

在這個例子中，我們要建立一個模型訓練任務。  
使用者提交 job 時，會提供資料集 ID、演算法名稱與訓練參數。

以下範例中的 `get_data()` 與 `train()` 為示意函式，請替換為你自己的實作。

```python
from typing import Any, Literal

import msgspec

from autocrud.types import Job, Resource


class TrainingPayload(msgspec.Struct):
    data_id: str
    algo: Literal["random-forest", "mlp"]
    params: dict[str, Any]


class TrainingJob(Job[TrainingPayload]):
    pass


def training(job: Resource[TrainingJob]) -> TrainingJob:
    print(f"start training job created by {job.info.created_by}")

    data = get_data(job.data.payload.data_id)
    model = train(
        job.data.payload.algo,
        data,
        job.data.payload.params,
    )

    print(f"trained model id: {model.id}")
    return job.data
```

在這裡：

- `TrainingPayload` 定義這次 job 的輸入
- `TrainingJob` 是實際註冊到 autocrud 的 job type
- `training()` 則是這個 job 對應的 handler，負責真正執行任務邏輯

---

在這個 Quickstart 中，我們使用最簡單的 job 定義方式。

autocrud 也支援更進階的功能，例如：

- 為 job 定義 artifact（輸出結果）
- 在 handler 中注入 job context

這些功能將在後續文件中介紹。

## 2. 在 autocrud 中註冊 job type

定義完 schema 與 handler 後，就可以將這個 job type 註冊到 autocrud。

```python
from autocrud import Schema, crud

crud.add_model(
    Schema(TrainingJob, "v1"),
    job_handler=training,
)
```

完成註冊後，autocrud 就會知道：

- 這個 job 的 schema 是 `TrainingJob`
- 這個 job 要由 `training` handler 來執行

## 3. 啟動 job consumer

最後，取得對應的 resource manager，並啟動 job consumer，讓系統開始處理進入 queue 的 job。

```python
mgr = crud.get_resource_manager(TrainingJob)
mgr.start_consume(
    # block=False  # 如果在同一個 process 內啟動，建議設為 False 以避免阻塞
)
```

啟動後，系統就會開始持續監聽 queue，並在有新的 `training-job` 進入時自動呼叫 `training()` handler 進行處理。

如果你是在同一個 process 中同時啟動 consumer 與提交 job，請記得設 `block=False`，避免 consumer 阻塞後續程式。

## 4. 添加新任務

完成 job type 註冊並啟動 consumer 後，就可以開始建立新的 job。

在 Quickstart 中，我們會使用最直接的方式：透過 Python API 建立 job。

### 4.1 使用 `ResourceManager.create()` 建立 job

```python
job_info = mgr.create(
    TrainingJob(
        payload=TrainingPayload(
            data_id="data:1",
            algo="random-forest",
            params={"n": 100},
        )
    )
)
```

建立後，這筆 job 會被加入 queue，並由先前啟動的 consumer 取出執行。

如果你在 console 中看到 handler 的輸出（例如 `start training job ...`），代表這筆 job 已成功進入 queue，並開始由 consumer 處理。

---

除了 Python API，autocrud 也支援透過 HTTP API 與 Web UI 建立 job，適合用於服務整合或人工操作。

- [Routes generation (FastAPI)](/howto/routes.md)
- [Web UI](/howto/web-ui.md)

## 5. 驗證 job 是否成功執行

在上一節中，我們已經提交了一個 job。

### 5.1 透過 console 輸出確認

如果一切正常，你應該可以在 console 中看到類似以下的輸出：

```text
start training job created by ...
```

這代表：

- job 已成功加入 queue
- consumer 正在正常運作
- handler 已被正確呼叫並開始執行

---

### 5.2 透過程式查詢 job 狀態

除了觀察 console 輸出，你也可以透過 `ResourceManager` 查詢 job 的狀態：

```python
from autocrud.types import TaskStatus

job = mgr.get(job_info.resource_id)
print(job.data.status)
```

由於 job 是非同步執行，剛建立後的狀態通常會是：

- `pending`：尚未被 consumer 取出
- `processing`：已開始執行

當 job 執行完成後，狀態會變成：

```python
TaskStatus.COMPLETED
```

### 等待 job 完成（簡單範例）

在實務上，你可以簡單輪詢（polling） job 狀態：

```python
import time
from autocrud.types import TaskStatus

job_id = job_info.resource_id

for _ in range(10):
    job = mgr.get(job_id)
    if job.data.status == TaskStatus.COMPLETED:
        break
    if job.data.status == TaskStatus.FAILED:
        raise RuntimeError(job.data.errmsg or "job failed")
    time.sleep(0.5)
else:
    raise TimeoutError("job did not complete in time")
```

### 常見問題

- 如果 job 在 1 秒以上仍然停留在 `pending`，很可能是 job handler 尚未啟動，請確認：

  - 是否已呼叫 `start_consume()`
  - 是否在正確的 process 中執行 consumer
  - queue backend 是否正常運作

- 如果狀態為 `failed`，可以查看錯誤訊息：

```python
print(job.data.errmsg)
```

這種透過程式查詢與驗證 job 狀態的方式，特別適合用於：

- 自動化測試
- service integration
- workflow chaining

## Appendix: 完整範例 script

以下是一份可直接複製的完整範例。  
其中的 `get_data()` 與 `train()` 為最小 stub，方便你快速驗證整體流程。

```python
import time
from typing import Any, Literal

import msgspec

from autocrud import Schema, crud
from autocrud.types import Job, Resource, TaskStatus


class TrainingPayload(msgspec.Struct):
    data_id: str
    algo: Literal["random-forest", "mlp"]
    params: dict[str, Any]



class TrainingJob(Job[TrainingPayload]):
    pass


def get_data(data_id: str) -> dict[str, Any]:
    return {
        "data_id": data_id,
        "rows": 100,
    }


class _Model:
    def __init__(self, model_id: str) -> None:
        self.id = model_id


def train(algo: str, data: dict[str, Any], params: dict[str, Any]) -> _Model:
    # 這裡用最小 stub 模擬訓練過程
    time.sleep(0.2)
    return _Model(model_id=f"{algo}-model-1")


def training(job: Resource[TrainingJob]) -> TrainingJob:
    print(f"start training job created by {job.info.created_by}")

    data = get_data(job.data.payload.data_id)
    model = train(
        job.data.payload.algo,
        data,
        job.data.payload.params,
    )

    print(f"trained model id: {model.id}")
    return job.data


def main() -> None:
    crud.add_model(
        Schema(TrainingJob, "v1"),
        job_handler=training,
    )

    mgr = crud.get_resource_manager(TrainingJob)

    # 如果你是在同一個 process 中同時提交 job 與啟動 consumer，
    # 請記得設 block=False，避免 consumer 阻塞後續程式。
    mgr.start_consume(block=False)

    job_info = mgr.create(
        TrainingJob(
            payload=TrainingPayload(
                data_id="data:1",
                algo="random-forest",
                params={"n": 100},
            )
        )
    )

    print("job submitted:", job_info.resource_id)

    # 簡單輪詢等待完成
    for _ in range(10):
        job = mgr.get(job_info.resource_id)
        print("current status:", job.data.status)

        if job.data.status == TaskStatus.COMPLETED:
            print("job completed")
            print("artifact:", job.data.artifact)
            break

        if job.data.status == TaskStatus.FAILED:
            raise RuntimeError(job.data.errmsg or "job failed")

        time.sleep(0.5)
    else:
        raise TimeoutError(
            "job did not complete in time; "
            "if it stays pending for more than 1 second, "
            "the job handler may not be started"
        )


if __name__ == "__main__":
    main()
```