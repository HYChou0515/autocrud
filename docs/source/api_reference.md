# API 參考

這裡包含 AutoCRUD 所有類和函數的詳細 API 文檔。

## 核心模組

### SingleModelCRUD 類

單個模型的 CRUD 操作核心類，支援泛型和高級功能。

```{eval-rst}
.. autoclass:: autocrud.core.SingleModelCRUD
   :members:
   :inherited-members:
   :show-inheritance:
```

### AutoCRUD 類（多模型）

支援多個模型的 AutoCRUD 系統，提供統一的管理介面。

```{eval-rst}
.. autoclass:: autocrud.multi_model.AutoCRUD
   :members:
   :inherited-members:
   :show-inheritance:
```

### ResourceNameStyle 枚舉

資源名稱命名風格枚舉。

```{eval-rst}
.. autoclass:: autocrud.multi_model.ResourceNameStyle
   :members:
   :inherited-members:
   :show-inheritance:
```

## 儲存後端

### Storage 抽象基類

```{eval-rst}
.. autoclass:: autocrud.storage.Storage
   :members:
   :inherited-members:
   :show-inheritance:
```

### MemoryStorage

記憶體儲存後端，適用於開發和測試。

```{eval-rst}
.. autoclass:: autocrud.storage.MemoryStorage
   :members:
   :inherited-members:
   :show-inheritance:
```

### DiskStorage

硬碟儲存後端，支援持久化和多種序列化格式。

```{eval-rst}
.. autoclass:: autocrud.storage.DiskStorage
   :members:
   :inherited-members:
   :show-inheritance:
```

## 儲存工廠

### StorageFactory

```{eval-rst}
.. autoclass:: autocrud.storage_factory.StorageFactory
   :members:
   :inherited-members:
   :show-inheritance:
```

### DefaultStorageFactory

```{eval-rst}
.. autoclass:: autocrud.storage_factory.DefaultStorageFactory
   :members:
   :inherited-members:
   :show-inheritance:
```

## 序列化器

### SerializerFactory

序列化工廠，支援多種序列化格式。

```{eval-rst}
.. autoclass:: autocrud.serializer.SerializerFactory
   :members:
   :inherited-members:
   :show-inheritance:
```

## FastAPI 產生器

### FastAPIGenerator

FastAPI 應用程式生成器。

```{eval-rst}
.. autoclass:: autocrud.fastapi_generator.FastAPIGenerator
   :members:
   :inherited-members:
   :show-inheritance:
```

## 模型轉換器

### ModelConverter

模型轉換器，支援多種資料模型格式。

```{eval-rst}
.. autoclass:: autocrud.converter.ModelConverter
   :members:
   :inherited-members:
   :show-inheritance:
```

## 元資料配置

### MetadataConfig

元資料配置類，用於設定時間戳和用戶追蹤。

```{eval-rst}
.. autoclass:: autocrud.metadata.MetadataConfig
   :members:
   :inherited-members:
   :show-inheritance:
```

## 查詢參數和結果

### ListQueryParams

列表查詢參數。

```{eval-rst}
.. autoclass:: autocrud.list_params.ListQueryParams
   :members:
   :inherited-members:
   :show-inheritance:
```

### ListResult

列表查詢結果。

```{eval-rst}
.. autoclass:: autocrud.list_params.ListResult
   :members:
   :inherited-members:
   :show-inheritance:
```

### SortOrder

排序順序枚舉。

```{eval-rst}
.. autoclass:: autocrud.list_params.SortOrder
   :members:
   :inherited-members:
   :show-inheritance:
```

### DateTimeRange

日期時間範圍查詢。

```{eval-rst}
.. autoclass:: autocrud.list_params.DateTimeRange
   :members:
   :inherited-members:
   :show-inheritance:
```

## 插件系統

### BaseRoutePlugin

路由插件基類。

```{eval-rst}
.. autoclass:: autocrud.plugin_system.BaseRoutePlugin
   :members:
   :inherited-members:
   :show-inheritance:
```

### PluginManager

插件管理器。

```{eval-rst}
.. autoclass:: autocrud.plugin_system.PluginManager
   :members:
   :inherited-members:
   :show-inheritance:
```

### PluginRouteConfig

插件路由配置。

```{eval-rst}
.. autoclass:: autocrud.plugin_system.PluginRouteConfig
   :members:
   :inherited-members:
   :show-inheritance:
```

### RouteMethod

HTTP 方法枚舉。

```{eval-rst}
.. autoclass:: autocrud.plugin_system.RouteMethod
   :members:
   :inherited-members:
   :show-inheritance:
```

## 路由配置

### RouteConfig

路由配置類。

```{eval-rst}
.. autoclass:: autocrud.route_config.RouteConfig
   :members:
   :inherited-members:
   :show-inheritance:
```

### RouteOptions

路由選項類。

```{eval-rst}
.. autoclass:: autocrud.route_config.RouteOptions
   :members:
   :inherited-members:
   :show-inheritance:
```

## 高級更新系統

### AdvancedUpdater

高級更新器，支援原子操作。

```{eval-rst}
.. autoclass:: autocrud.updater.AdvancedUpdater
   :members:
   :inherited-members:
   :show-inheritance:
```

### UpdateOperation

更新操作基類。

```{eval-rst}
.. autoclass:: autocrud.updater.UpdateOperation
   :members:
   :inherited-members:
   :show-inheritance:
```

### UpdateAction

更新動作枚舉。

```{eval-rst}
.. autoclass:: autocrud.updater.UpdateAction
   :members:
   :inherited-members:
   :show-inheritance:
```

## Schema 分析器

### SchemaAnalyzer

模型 Schema 分析器。

```{eval-rst}
.. autoclass:: autocrud.schema_analyzer.SchemaAnalyzer
   :members:
   :inherited-members:
   :show-inheritance:
```

## 預設插件

### DEFAULT_PLUGINS

預設插件列表，包含標準的 CRUD 操作插件。

```{eval-rst}
.. autodata:: autocrud.default_plugins.DEFAULT_PLUGINS
```

### 插件實例

```{eval-rst}
.. autodata:: autocrud.default_plugins.default_create_plugin
.. autodata:: autocrud.default_plugins.default_get_plugin  
.. autodata:: autocrud.default_plugins.default_update_plugin
.. autodata:: autocrud.default_plugins.default_delete_plugin
.. autodata:: autocrud.default_plugins.default_count_plugin
.. autodata:: autocrud.default_plugins.default_list_plugin
```

## 更新操作函數

### 值設定操作

```{eval-rst}
.. autofunction:: autocrud.updater.set_value
.. autofunction:: autocrud.updater.undefined
```

### 列表操作

```{eval-rst}
.. autofunction:: autocrud.updater.list_set
.. autofunction:: autocrud.updater.list_add
.. autofunction:: autocrud.updater.list_remove
```

### 字典操作

```{eval-rst}
.. autofunction:: autocrud.updater.dict_set
.. autofunction:: autocrud.updater.dict_update
.. autofunction:: autocrud.updater.dict_remove
```

```{eval-rst}
.. autodata:: autocrud.types.ModelType
.. autodata:: autocrud.types.DataDict
.. autodata:: autocrud.types.IDType
```
