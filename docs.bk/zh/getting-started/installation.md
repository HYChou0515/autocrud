---
title: 安裝指南
description: AutoCRUD 的安裝方式與依賴說明
---

# 安裝指南

## 系統需求

- Python >= 3.11
- pip 或 uv (推薦)

## 安裝方式

### 基本安裝

=== "使用 pip"

    ```bash
    pip install autocrud
    ```

=== "使用 uv"

    ```bash
    uv add autocrud
    ```

## 驗證安裝

安裝完成後，可以驗證 AutoCRUD 是否正確安裝：

```python
import autocrud
print(autocrud.__version__)
```

## 開發環境安裝

如果你想要參與 AutoCRUD 開發或運行測試：

```bash
# Clone repository
git clone https://github.com/HYChou0515/autocrud.git
cd autocrud

# 使用 uv 安裝開發依賴
uv sync --all-extras

# 運行測試
uv run pytest

# 生成文檔
uv run mkdocs serve
```

## 下一步

- [快速開始](quickstart.md) - 學習如何建立第一個 API