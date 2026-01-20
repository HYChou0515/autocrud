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

### 可選依賴

#### S3 儲存支援

如果需要使用 AWS S3 或相容的物件儲存（如 MinIO）：

=== "使用 pip"

    ```bash
    pip install "autocrud[s3]"
    ```

=== "使用 uv"

    ```bash
    uv add "autocrud[s3]"
    ```

#### Content-Type 自動偵測

如果需要 BlobStore 自動偵測檔案的 MIME 類型：

=== "使用 pip"

    ```bash
    pip install "autocrud[magic]"
    ```

=== "使用 uv"

    ```bash
    uv add "autocrud[magic]"
    ```

!!! warning "python-magic 系統依賴"
    `autocrud[magic]` 依賴 `python-magic`，需要系統安裝 `libmagic`：
    
    === "Ubuntu/Debian"
        ```bash
        sudo apt-get install libmagic1
        ```
    
    === "macOS"
        ```bash
        brew install libmagic
        ```
    
    === "Windows"
        請參考 [python-magic 安裝說明](https://github.com/ahupp/python-magic#installation)

#### 完整安裝

安裝所有可選依賴：

=== "使用 pip"

    ```bash
    pip install "autocrud[s3,magic]"
    ```

=== "使用 uv"

    ```bash
    uv add "autocrud[s3,magic]"
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