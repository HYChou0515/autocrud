# Quickstart

我們設想了幾個可能的應用場景, 可以根據需求從不同的角度出發使用autocrud解決您的問題。

1. 我想要快速demo我的businses logic -> [fast demo](/quickstart/fast-demo.md)
1. 我想要在現有的程式碼使用autocrud的功能 -> [integrate](/quickstart/integrate-existing.md)
1. 我想使用job queue包含所有常見配套 -> [job queue](/quickstart/job-queue.md)
1. 我不想寫前端
1. schema變動我想要做資料migration
1. 我想要讓我的data都內建版本控制, 軟刪除, 軟更新
1. 我希望我能自訂post data的API
1. 我希望需要處理較久的data可以在background執行

This quickstart uses `DiskStorageFactory` as the **minimal viable** persistent backend.

## Install

```bash
pip install autocrud
```

## Minimal FastAPI app

```python
from pathlib import Path
from fastapi import FastAPI
from msgspec import Struct

from autocrud import crud
from autocrud.resource_manager.storage_factory import DiskStorageFactory

class User(Struct):
    name: str
    age: int

app = FastAPI()

# 1) configure once at startup (global instance pattern)
crud.configure(
    storage_factory=DiskStorageFactory(Path("./data")),
    model_naming="kebab",
)

# 2) register models
crud.add_model(User)

# 3) generate routes
crud.apply(app)
```

## What to check next

* Route generation and customization: `docs/howto/routes.md`
* Storage backends overview: `docs/guides/storage.md`
* Why msgspec Struct is used as schema: `docs/concepts/schema.md`

