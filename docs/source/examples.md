# 💡 使用案例

## 📁 可用範例

- `quick_start.py` - 基本 CRUD 操作
- `resource_crud.py` - 完整功能演示
- `schema_upgrade.py` - 數據遷移  
- `backup.py` - 備份與還原

## � 完整程式碼

### 基本 CRUD 操作 (quick_start.py)

```{literalinclude} ../../examples/quick_start.py
:language: python
:linenos:
```

### 完整功能演示 (resource_crud.py)

```{literalinclude} ../../examples/resource_crud.py
:language: python
:linenos:
```

### 數據遷移 (schema_upgrade.py)

```{literalinclude} ../../examples/schema_upgrade.py
:language: python
:linenos:
```

### 備份與還原 (backup.py)

```{literalinclude} ../../examples/backup.py
:language: python
:linenos:
```

## 🔍 自動生成的端點

| 方法 | 路徑 | 功能 |
|------|------|------|
| `POST` | `/model` | 創建資源 |
| `GET` | `/model/{id}/data` | 獲取數據 |
| `GET` | `/model/{id}/meta` | 獲取元數據 |
| `GET` | `/model/{id}/full` | 獲取完整資源 |
| `PUT` | `/model/{id}` | 完整更新 |
| `PATCH` | `/model/{id}` | JSON Patch 更新 |
| `DELETE` | `/model/{id}` | 軟刪除 |
| `GET` | `/model/data` | 列出所有數據 |
| `GET` | `/model/meta` | 列出所有元數據 |
| `GET` | `/model/full` | 列出完整資源 |
| `POST` | `/model/{id}/switch/{revision}` | 版本切換 |
| `POST` | `/model/{id}/restore` | 恢復已刪除 |

## 🚀 運行範例

```bash
# 基本範例
python examples/quick_start.py
python examples/resource_crud.py

# 數據遷移
python examples/schema_upgrade.py

# 備份還原
python examples/backup.py

# 不同數據類型
python examples/quick_start.py pydantic
python examples/resource_crud.py dataclass

# 開發服務器
python -m fastapi dev examples/quick_start.py
```