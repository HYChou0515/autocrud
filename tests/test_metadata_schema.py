"""
測試 Metadata 和 Schema 分析功能
"""

from dataclasses import dataclass
from typing import Optional

from autocrud import SingleModelCRUD, MemoryStorage, MetadataConfig, SchemaAnalyzer


@dataclass
class UserWithMetadata:
    """完整的用戶模型，包含所有 metadata 欄位"""

    id: str
    name: str
    email: str
    age: Optional[int] = None
    created_time: Optional[str] = None
    updated_time: Optional[str] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None


@dataclass
class ProductWithCustomID:
    """使用自定義 ID 欄位名稱的產品模型"""

    pk: str
    title: str
    price: float
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class TestMetadataConfig:
    """測試 MetadataConfig 類"""

    def test_default_config(self):
        """測試預設配置"""
        config = MetadataConfig()
        assert config.id_field == "id"
        assert config.enable_timestamps is False
        assert config.enable_user_tracking is False

    def test_with_timestamps(self):
        """測試時間戳配置"""
        config = MetadataConfig.with_timestamps()
        assert config.enable_timestamps is True
        assert config.created_time_field == "created_time"
        assert config.updated_time_field == "updated_time"

    def test_with_user_tracking(self):
        """測試用戶追蹤配置"""
        config = MetadataConfig.with_user_tracking()
        assert config.enable_user_tracking is True
        assert config.created_by_field == "created_by"
        assert config.updated_by_field == "updated_by"

    def test_with_full_tracking(self):
        """測試完整追蹤配置"""
        config = MetadataConfig.with_full_tracking()
        assert config.enable_timestamps is True
        assert config.enable_user_tracking is True

    def test_custom_field_names(self):
        """測試自定義欄位名稱"""
        config = MetadataConfig.with_full_tracking(
            id_field="pk",
            created_time_field="created_at",
            updated_time_field="updated_at",
            created_by_field="creator",
            updated_by_field="updater",
        )
        assert config.id_field == "pk"
        assert config.created_time_field == "created_at"
        assert config.updated_time_field == "updated_at"
        assert config.created_by_field == "creator"
        assert config.updated_by_field == "updater"

    def test_get_metadata_fields(self):
        """測試獲取 metadata 欄位"""
        config = MetadataConfig.with_full_tracking()
        fields = config.get_metadata_fields()

        assert "id" in fields
        assert "created_time" in fields
        assert "updated_time" in fields
        assert "created_by" in fields
        assert "updated_by" in fields

    def test_get_create_excluded_fields(self):
        """測試獲取 create 時排除的欄位"""
        config = MetadataConfig.with_full_tracking()
        excluded = config.get_create_excluded_fields()

        assert "id" in excluded
        assert "created_time" in excluded
        assert "updated_time" in excluded
        assert "updated_by" in excluded

    def test_get_update_excluded_fields(self):
        """測試獲取 update 時排除的欄位"""
        config = MetadataConfig.with_full_tracking()
        excluded = config.get_update_excluded_fields()

        assert "id" in excluded
        assert "created_time" in excluded
        assert "updated_time" in excluded
        assert "created_by" in excluded

    def test_apply_create_metadata(self):
        """測試應用 create metadata"""

        def mock_time():
            return "2023-01-01T00:00:00"

        def mock_user():
            return "test_user"

        config = MetadataConfig.with_full_tracking(
            get_current_time=mock_time, get_current_user=mock_user
        )

        data = {"name": "John", "email": "john@example.com"}
        result = config.apply_create_metadata(data)

        assert result["name"] == "John"
        assert result["email"] == "john@example.com"
        assert result["created_time"] == "2023-01-01T00:00:00"
        assert result["updated_time"] == "2023-01-01T00:00:00"
        assert result["created_by"] == "test_user"
        assert result["updated_by"] == "test_user"

    def test_apply_update_metadata(self):
        """測試應用 update metadata"""

        def mock_time():
            return "2023-01-02T00:00:00"

        def mock_user():
            return "updater_user"

        config = MetadataConfig.with_full_tracking(
            get_current_time=mock_time, get_current_user=mock_user
        )

        data = {"name": "Jane"}
        result = config.apply_update_metadata(data)

        assert result["name"] == "Jane"
        assert result["updated_time"] == "2023-01-02T00:00:00"
        assert result["updated_by"] == "updater_user"
        assert "created_time" not in result
        assert "created_by" not in result


class TestSchemaAnalyzer:
    """測試 SchemaAnalyzer 類"""

    def test_analyze_full_schema(self):
        """測試分析完整 schema"""
        config = MetadataConfig.with_full_tracking()
        analyzer = SchemaAnalyzer(UserWithMetadata, config)

        # 檢查是否正確識別所有欄位
        assert "id" in analyzer.field_types
        assert "name" in analyzer.field_types
        assert "email" in analyzer.field_types
        assert "created_time" in analyzer.field_types

    def test_get_create_model(self):
        """測試獲取 create 請求模型"""
        config = MetadataConfig.with_full_tracking()
        analyzer = SchemaAnalyzer(UserWithMetadata, config)

        CreateModel = analyzer.get_create_model()
        assert CreateModel.__name__ == "UserWithMetadataCreateRequest"

        # 檢查 create 模型的欄位
        fields = CreateModel.model_fields
        assert "name" in fields
        assert "email" in fields
        assert "age" in fields
        assert "id" not in fields  # ID 應該被排除
        assert "created_time" not in fields  # 時間戳應該被排除
        assert "updated_time" not in fields

    def test_get_update_model(self):
        """測試獲取 update 請求模型"""
        config = MetadataConfig.with_full_tracking()
        analyzer = SchemaAnalyzer(UserWithMetadata, config)

        UpdateModel = analyzer.get_update_model()
        assert UpdateModel.__name__ == "UserWithMetadataUpdateRequest"

        # 檢查 update 模型的欄位（大部分應該都是可選的）
        fields = UpdateModel.model_fields
        assert "name" in fields
        assert "email" in fields
        assert "age" in fields
        assert "id" not in fields  # ID 應該被排除
        assert "created_time" not in fields  # 創建時間應該被排除

    def test_get_response_model(self):
        """測試獲取響應模型"""
        config = MetadataConfig.with_full_tracking()
        analyzer = SchemaAnalyzer(UserWithMetadata, config)

        ResponseModel = analyzer.get_response_model()
        assert ResponseModel.__name__ == "UserWithMetadataResponse"

        # 檢查響應模型包含所有欄位
        fields = ResponseModel.model_fields
        assert "id" in fields
        assert "name" in fields
        assert "email" in fields
        assert "created_time" in fields
        assert "updated_time" in fields

    def test_custom_id_field(self):
        """測試自定義 ID 欄位"""
        config = MetadataConfig.with_timestamps(
            id_field="pk",
            created_time_field="created_at",
            updated_time_field="updated_at",
        )
        analyzer = SchemaAnalyzer(ProductWithCustomID, config)

        assert analyzer.get_id_field_name() == "pk"

        CreateModel = analyzer.get_create_model()
        fields = CreateModel.model_fields
        assert "title" in fields
        assert "price" in fields
        assert "pk" not in fields  # 自定義 ID 應該被排除
        assert "created_at" not in fields  # 時間戳應該被排除


class TestSingleModelCRUDWithMetadata:
    """測試 SingleModelCRUD 與 metadata 功能的整合"""

    def setup_method(self):
        """設置測試環境"""
        self.storage = MemoryStorage()

        # 模擬時間和用戶函數
        self.current_time = "2023-01-01T00:00:00"
        self.current_user = "test_user"

        def mock_time():
            return self.current_time

        def mock_user():
            return self.current_user

        self.metadata_config = MetadataConfig.with_full_tracking(
            get_current_time=mock_time, get_current_user=mock_user
        )

        self.crud = SingleModelCRUD(
            model=UserWithMetadata,
            storage=self.storage,
            resource_name="users",
            metadata_config=self.metadata_config,
        )

    def test_create_with_metadata(self):
        """測試帶 metadata 的創建"""
        user_data = {"name": "John Doe", "email": "john@example.com", "age": 30}

        user_id = self.crud.create(user_data)
        result = self.crud.get(user_id)

        # 檢查基本數據
        assert result["name"] == "John Doe"
        assert result["email"] == "john@example.com"
        assert result["age"] == 30

        # 檢查自動添加的 metadata
        assert "id" in result
        assert result["created_time"] == "2023-01-01T00:00:00"
        assert result["updated_time"] == "2023-01-01T00:00:00"
        assert result["created_by"] == "test_user"
        assert result["updated_by"] == "test_user"

    def test_update_with_metadata(self):
        """測試帶 metadata 的更新"""
        # 先創建一個用戶
        user_data = {"name": "John Doe", "email": "john@example.com"}
        created_user_id = self.crud.create(user_data)
        user_id = created_user_id

        # 模擬時間推進和用戶變更
        self.current_time = "2023-01-02T00:00:00"
        self.current_user = "updater_user"

        # 更新用戶
        update_data = {"name": "Jane Doe", "age": 25}
        assert self.crud.update(user_id, update_data)
        result = self.crud.get(user_id)

        # 檢查更新的數據
        assert result["name"] == "Jane Doe"
        assert result["age"] == 25
        assert result["email"] == "john@example.com"  # 保持不變

        # 檢查 metadata 更新
        assert result["created_time"] == "2023-01-01T00:00:00"  # 創建時間不變
        assert result["created_by"] == "test_user"  # 創建者不變
        assert result["updated_time"] == "2023-01-02T00:00:00"  # 更新時間變更
        assert result["updated_by"] == "updater_user"  # 更新者變更

    def test_advanced_update_with_metadata(self):
        """測試 advanced update 與 metadata"""
        # 先創建一個用戶
        user_data = {"name": "John Doe", "email": "john@example.com"}
        created_user_id = self.crud.create(user_data)
        user_id = created_user_id

        # 模擬時間推進
        self.current_time = "2023-01-03T00:00:00"
        self.current_user = "advanced_updater"

        # 使用 advanced update
        update_data = {
            "name": {"_action": "set", "value": "Advanced Jane"},
            "age": {"_action": "set", "value": 35},
        }
        result = self.crud.advanced_update(user_id, update_data)

        # 檢查更新的數據
        assert result["name"] == "Advanced Jane"
        assert result["age"] == 35

        # 檢查 metadata 更新
        assert result["updated_time"] == "2023-01-03T00:00:00"
        assert result["updated_by"] == "advanced_updater"

    def test_custom_id_field_crud(self):
        """測試自定義 ID 欄位的 CRUD 操作"""
        config = MetadataConfig.with_timestamps(
            id_field="pk",
            created_time_field="created_at",
            updated_time_field="updated_at",
        )

        crud = SingleModelCRUD(
            model=ProductWithCustomID,
            storage=MemoryStorage(),
            resource_name="products",
            metadata_config=config,
        )

        product_data = {"title": "Test Product", "price": 99.99}

        result_id = crud.create(product_data)
        result = crud.get(result_id)

        # 檢查自定義 ID 欄位
        assert "pk" in result
        assert result["title"] == "Test Product"
        assert result["price"] == 99.99
        assert "created_at" in result
        assert "updated_at" in result
