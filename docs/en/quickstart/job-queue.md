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

在接下來的章節中，我們會一步一步帶你建立一個完整可用的 job queue 系統。