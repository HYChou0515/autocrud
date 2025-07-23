# API 參考

這裡包含 AutoCRUD 所有類和函數的詳細 API 檔案。

## 核心模組

### AutoCRUD 類

```{eval-rst}
.. autoclass:: autocrud.core.AutoCRUD
   :members:
   :inherited-members:
   :show-inheritance:
```

### MultiModelAutoCRUD 類

```{eval-rst}
.. autoclass:: autocrud.multi_model.MultiModelAutoCRUD
   :members:
   :inherited-members:
   :show-inheritance:
```

## 儲存後端

### MemoryStorage

```{eval-rst}
.. autoclass:: autocrud.storage.MemoryStorage
   :members:
   :inherited-members:
   :show-inheritance:
```

### DiskStorage

```{eval-rst}
.. autoclass:: autocrud.storage.DiskStorage
   :members:
   :inherited-members:
   :show-inheritance:
```

## 序列化器

### SerializerFactory

```{eval-rst}
.. autoclass:: autocrud.serializer.SerializerFactory
   :members:
   :inherited-members:
   :show-inheritance:
```

## FastAPI 產生器

### FastAPIGenerator

```{eval-rst}
.. autoclass:: autocrud.fastapi_generator.FastAPIGenerator
   :members:
   :inherited-members:
   :show-inheritance:
```

## 模型轉換器

### ModelConverter

```{eval-rst}
.. autoclass:: autocrud.converter.ModelConverter
   :members:
   :inherited-members:
   :show-inheritance:
```

## 異常類

### AutoCRUDError

```{eval-rst}
.. autoexception:: autocrud.exceptions.AutoCRUDError
```

### ValidationError

```{eval-rst}
.. autoexception:: autocrud.exceptions.ValidationError
```

### StorageError

```{eval-rst}
.. autoexception:: autocrud.exceptions.StorageError
```

## 類型定義

### 常用類型

```{eval-rst}
.. autodata:: autocrud.types.ModelType
.. autodata:: autocrud.types.DataDict
.. autodata:: autocrud.types.IDType
```
