# 🛠️ 安裝指南

本指南詳細說明如何在不同環境中安裝和配置 AutoCRUD。

## 系統需求

### 基本要求
- **Python**: 3.8 或更高版本
- **操作系統**: Windows, macOS, Linux
- **內存**: 最少 512MB RAM
- **存儲**: 至少 100MB 可用空間

### 推薦環境
- **Python**: 3.11+ (最佳性能)
- **內存**: 2GB+ RAM
- **虛擬環境**: 使用 venv, conda, 或 poetry

## 快速安裝

::::{tab-set}

:::{tab-item} pip
```bash
# 基本安裝
pip install autocrud

# 包含所有可選依賴
pip install autocrud[all]
```
:::

:::{tab-item} uv (推薦)
```bash
# 基本安裝
uv add autocrud

# 開發環境安裝
uv add autocrud --dev
```
:::

:::{tab-item} poetry
```bash
# 基本安裝
poetry add autocrud

# 開發依賴
poetry add autocrud --group dev
```
:::

:::{tab-item} conda
```bash
# 通過 pip 在 conda 環境中安裝
conda install pip
pip install autocrud
```
:::

::::

## 可選依賴

AutoCRUD 提供多個可選功能包：

### 數據驗證
```bash
# Pydantic v2 支持 (推薦)
pip install autocrud[pydantic]

# msgspec 高性能支持
pip install autocrud[msgspec]
```

### 數據庫支持
```bash
# PostgreSQL 支持
pip install autocrud[postgresql]

# MySQL 支持  
pip install autocrud[mysql]

# MongoDB 支持
pip install autocrud[mongodb]

# Redis 支持
pip install autocrud[redis]
```

### 開發工具
```bash
# 測試工具
pip install autocrud[testing]

# 文檔生成
pip install autocrud[docs]

# 完整開發環境
pip install autocrud[dev]
```

### 完整安裝
```bash
# 安裝所有功能
pip install autocrud[all]
```

## 虛擬環境設置

### 使用 venv (推薦)

::::{tab-set}

:::{tab-item} Linux/macOS
```bash
# 創建虛擬環境
python -m venv autocrud-env

# 激活環境
source autocrud-env/bin/activate

# 安裝 AutoCRUD
pip install autocrud

# 退出環境
deactivate
```
:::

:::{tab-item} Windows
```cmd
# 創建虛擬環境
python -m venv autocrud-env

# 激活環境
autocrud-env\Scripts\activate

# 安裝 AutoCRUD
pip install autocrud

# 退出環境
deactivate
```
:::

::::

### 使用 conda

```bash
# 創建 conda 環境
conda create -n autocrud python=3.11

# 激活環境
conda activate autocrud

# 安裝 AutoCRUD
pip install autocrud

# 退出環境
conda deactivate
```

### 使用 Poetry

```bash
# 初始化新項目
poetry new my-autocrud-project
cd my-autocrud-project

# 添加 AutoCRUD
poetry add autocrud

# 激活 shell
poetry shell

# 或直接運行
poetry run python main.py
```

## 驗證安裝

創建一個簡單的測試文件來驗證安裝：

```python
# test_installation.py
from autocrud.crud.core import AutoCRUD
from pydantic import BaseModel

class TestModel(BaseModel):
    name: str
    value: int

# 創建 CRUD 實例
crud = AutoCRUD()
print("✅ AutoCRUD 安裝成功！")
print(f"版本: {crud.__version__ if hasattr(crud, '__version__') else '未知'}")
```

運行測試：
```bash
python test_installation.py
```

## 開發環境設置

### 從源碼安裝

```bash
# 克隆倉庫
git clone https://github.com/HYChou0515/autocrud.git
cd autocrud

# 使用 uv (推薦)
uv sync --dev

# 或使用 pip
pip install -e .[dev]

# 運行測試
uv run pytest
# 或
python -m pytest
```

### 設置 pre-commit 鈎子

```bash
# 安裝 pre-commit
pip install pre-commit

# 設置鈎子
pre-commit install

# 手動運行檢查
pre-commit run --all-files
```

## Docker 安裝

### 官方 Docker 鏡像

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安裝 AutoCRUD
RUN pip install autocrud[all]

# 複製應用代碼
COPY . .

# 暴露端口
EXPOSE 8000

# 啟動命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ENVIRONMENT=production
    depends_on:
      - db

  db:
    image: postgres:15
    environment:
      POSTGRES_DB: autocrud
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

## 生產部署

### 基本 requirements.txt

```txt
# requirements.txt
autocrud[all]==1.0.0
uvicorn[standard]==0.25.0
gunicorn==21.2.0
```

### 使用 Gunicorn

```bash
# 安裝 Gunicorn
pip install gunicorn

# 啟動服務
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker
```

### 使用 systemd (Linux)

```ini
# /etc/systemd/system/autocrud.service
[Unit]
Description=AutoCRUD API
After=network.target

[Service]
Type=exec
User=www-data
Group=www-data
WorkingDirectory=/opt/autocrud
ExecStart=/opt/autocrud/venv/bin/gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker
Restart=always

[Install]
WantedBy=multi-user.target
```

啟動服務：
```bash
sudo systemctl enable autocrud
sudo systemctl start autocrud
sudo systemctl status autocrud
```

## 環境變量配置

創建 `.env` 文件：

```env
# .env
# 基本配置
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=info

# API 配置
API_TITLE=My AutoCRUD API
API_VERSION=1.0.0
API_PREFIX=/api/v1

# 數據庫配置
DATABASE_URL=postgresql://user:password@localhost/autocrud
REDIS_URL=redis://localhost:6379/0

# 安全配置
SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=localhost,127.0.0.1,yourdomain.com

# 性能配置
WORKERS=4
MAX_CONNECTIONS=100
TIMEOUT=30
```

## 性能優化

### 基本優化

```python
# main.py
import os
from autocrud.crud.core import AutoCRUD

# 根據環境調整配置
is_production = os.getenv("ENVIRONMENT") == "production"

crud = AutoCRUD(
    # 生產環境優化
    enable_cache=is_production,
    cache_ttl=3600 if is_production else 60,
    batch_size=100 if is_production else 10,
)
```

### 內存優化

```bash
# 設置 Python 內存限制
export PYTHONMALLOC=malloc
export MALLOC_ARENA_MAX=2

# 限制進程內存使用
ulimit -v 1048576  # 1GB 虛擬內存限制
```

## 常見問題

### 安裝問題

#### pip 安裝失敗
```bash
# 升級 pip
pip install --upgrade pip

# 清除緩存
pip cache purge

# 使用國內鏡像
pip install autocrud -i https://pypi.tuna.tsinghua.edu.cn/simple/
```

#### 依賴衝突
```bash
# 檢查依賴樹
pip show autocrud

# 創建新的虛擬環境
python -m venv fresh-env
source fresh-env/bin/activate
pip install autocrud
```

### 運行時問題

#### 導入錯誤
```python
# 檢查安裝路徑
import sys
print(sys.path)

import autocrud
print(autocrud.__file__)
```

#### 版本檢查
```python
import autocrud
print(f"AutoCRUD 版本: {autocrud.__version__}")

import fastapi
print(f"FastAPI 版本: {fastapi.__version__}")
```

### 性能問題

#### 啟動慢
```python
# 禁用自動發現功能
crud = AutoCRUD(auto_discover=False)

# 延遲加載模型
crud.lazy_load = True
```

#### 內存使用高
```python
# 限制緩存大小
crud = AutoCRUD(
    enable_cache=True,
    cache_size=1000,  # 限制緩存條目數
    cache_ttl=300     # 5分鐘過期
)
```

## 升級指南

### 從舊版本升級

```bash
# 檢查當前版本
pip show autocrud

# 升級到最新版本
pip install --upgrade autocrud

# 檢查更改日誌
pip show autocrud | grep Version
```

### 重大版本更新

在升級前請查看 [更改日誌](changelog.md) 了解重大變更。

### 數據遷移

```python
# migration.py
from autocrud.migration import migrate_data

# 自動遷移存儲格式
migrate_data(
    from_version="0.9.x",
    to_version="1.0.x",
    backup=True
)
```

## 獲取幫助

如果遇到安裝問題：

1. 📖 查看 [常見問題](user_guide.md#常見問題)
2. 🐛 搜索 [GitHub Issues](https://github.com/HYChou0515/autocrud/issues)
3. 💬 發起新的 [討論](https://github.com/HYChou0515/autocrud/discussions)
4. 📧 聯繫支持團隊

## 下一步

安裝完成後，建議：

1. 🚀 閱讀 [快速開始](quickstart.md) 指南
2. 📖 瀏覽 [用戶指南](user_guide.md)
3. 💡 查看 [示例集合](examples.md)
4. 🔧 探索 [API 參考](api_reference.md)
