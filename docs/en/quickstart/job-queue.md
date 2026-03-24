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

首先，我們先定義這個 job 的輸入（`Payload`）、輸出產物（`Artifact`），以及對應的 job type。

在這個例子中，我們要建立一個模型訓練任務。  
使用者提交 job 時，會提供資料集 ID、演算法名稱與訓練參數；而 job 執行完成後，則會產生一個 `model_id` 作為訓練結果。

```python
from typing import Any, Literal

import msgspec

from autocrud.types import Job, Resource


class TrainingPayload(msgspec.Struct):
    data_id: str
    algo: Literal["random-forest", "mlp"]
    params: dict[str, Any]


class TrainingArtifact(msgspec.Struct):
    model_id: str


class TrainingJob(Job[TrainingPayload, TrainingArtifact]):
    pass


def training(job: Resource[TrainingJob]) -> TrainingJob:
    print(f"start training job created by {job.info.created_by}")

    data = get_data(job.data.payload.data_id)
    model = train(
        job.data.payload.algo,
        data,
        job.data.payload.params,
    )

    job.data.artifact = TrainingArtifact(model_id=model.id)
    return job.data
```

在這裡：

- `TrainingPayload` 定義這次 job 的輸入
- `TrainingArtifact` 定義這次 job 執行後的輸出結果
- `TrainingJob` 是實際註冊到 autocrud 的 job type
- `training()` 則是這個 job 對應的 handler，負責真正執行任務邏輯

## 2. 在 autocrud 中註冊 job type

定義完 schema 與 handler 後，就可以將這個 job type 註冊到 autocrud。

```python
from autocrud import Schema, crud

crud.add(
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
mgr = crud.get_resource_manager("training-job")
mgr.start_consume(
    # block=False  # 如果在同一個 process 內啟動，建議設為 False 以避免阻塞
)
```

啟動後，系統就會開始持續監聽 queue，並在有新的 `training-job` 進入時自動呼叫 `training()` handler 進行處理。