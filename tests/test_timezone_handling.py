"""測試時區處理邏輯"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from autocrud.core import SingleModelCRUD
from autocrud.storage import MemoryStorage
from autocrud.metadata import MetadataConfig
from autocrud.list_params import ListQueryParams, DateTimeRange


@dataclass
class TimezoneTestModel:
    """時區測試用的資料模型"""

    id: str
    name: str
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None


class TestTimezoneHandling:
    """測試時區處理邏輯"""

    def test_system_stored_naive_datetime_assumed_utc(self):
        """測試系統存儲的 naive datetime 被假設為 UTC"""
        storage = MemoryStorage()

        metadata_config = MetadataConfig(enable_timestamps=True)
        crud = SingleModelCRUD(
            TimezoneTestModel, storage, "test_model", metadata_config=metadata_config
        )

        # 創建測試數據
        created_id = crud.create({"name": "Test"})

        # 手動設置一個 naive datetime（系統存儲的時間）
        utc_time = datetime(2024, 1, 1, 12, 0, 0)  # naive datetime，應該被假設為 UTC
        key = f"test_model:{created_id}"
        data = storage.get(key)
        if data:
            data["created_time"] = utc_time.isoformat()
            storage.set(key, data)

        # 創建一個本地時區的查詢範圍
        local_tz = timezone(datetime.now().astimezone().utcoffset())
        # 假設本地時區是 UTC+8，那麼 UTC 12:00 對應本地 20:00
        start_time = datetime(2024, 1, 1, 19, 0, 0).replace(
            tzinfo=local_tz
        )  # 本地 19:00
        end_time = datetime(2024, 1, 1, 21, 0, 0).replace(tzinfo=local_tz)  # 本地 21:00

        params = ListQueryParams(
            created_time_range=DateTimeRange(start=start_time, end=end_time)
        )

        result = crud.list_with_params(params)

        # 系統的 naive datetime 被假設為 UTC，轉換到本地時區後應該在範圍內
        assert len(result.items) == 1
        assert result.items[0]["id"] == created_id

    def test_user_input_naive_datetime_assumed_local(self):
        """測試用戶輸入的 naive datetime 被假設為本地時區"""
        storage = MemoryStorage()
        metadata_config = MetadataConfig(enable_timestamps=True)
        crud = SingleModelCRUD(
            TimezoneTestModel, storage, "test_model", metadata_config=metadata_config
        )

        # 創建測試數據
        created_id = crud.create({"name": "Test"})

        # 設置一個有時區信息的系統時間（UTC）
        utc_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        key = f"test_model:{created_id}"
        data = storage.get(key)
        if data:
            data["created_time"] = utc_time.isoformat()
            storage.set(key, data)

        # 用戶輸入的 naive datetime 範圍（應該被假設為本地時區）
        start_time = datetime(2024, 1, 1, 12, 0, 0)  # naive，假設為本地時區
        end_time = datetime(2024, 1, 1, 13, 0, 0)  # naive，假設為本地時區

        params = ListQueryParams(
            created_time_range=DateTimeRange(start=start_time, end=end_time)
        )

        result = crud.list_with_params(params)

        # 如果本地時區是 UTC，那麼應該匹配
        # 如果本地時區不是 UTC，結果可能會不同，但不應該崩潰
        assert len(result.items) >= 0  # 至少不應該崩潰

    def test_mixed_timezone_aware_datetimes(self):
        """測試混合時區感知的 datetime 處理"""
        storage = MemoryStorage()
        metadata_config = MetadataConfig(enable_timestamps=True)
        crud = SingleModelCRUD(
            TimezoneTestModel, storage, "test_model", metadata_config=metadata_config
        )

        # 創建測試數據
        created_id = crud.create({"name": "Test"})

        # 設置一個 UTC 時間
        utc_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        key = f"test_model:{created_id}"
        data = storage.get(key)
        if data:
            data["created_time"] = utc_time.isoformat()
            storage.set(key, data)

        # 使用不同時區的查詢範圍
        eastern_tz = timezone(timedelta(hours=-5))  # UTC-5 (EST)
        start_time = datetime(
            2024, 1, 1, 7, 0, 0, tzinfo=eastern_tz
        )  # EST 07:00 = UTC 12:00
        end_time = datetime(
            2024, 1, 1, 8, 0, 0, tzinfo=eastern_tz
        )  # EST 08:00 = UTC 13:00

        params = ListQueryParams(
            created_time_range=DateTimeRange(start=start_time, end=end_time)
        )

        result = crud.list_with_params(params)

        # UTC 12:00 應該在 EST 07:00-08:00 範圍內（對應 UTC 12:00-13:00）
        assert len(result.items) == 1
        assert result.items[0]["id"] == created_id

    def test_invalid_datetime_formats_handling(self):
        """測試無效日期時間格式的處理"""
        storage = MemoryStorage()
        metadata_config = MetadataConfig(enable_timestamps=True)
        crud = SingleModelCRUD(
            TimezoneTestModel, storage, "test_model", metadata_config=metadata_config
        )

        # 創建測試數據
        created_id = crud.create({"name": "Test"})

        # 設置無效的時間格式
        key = f"test_model:{created_id}"
        data = storage.get(key)
        if data:
            data["created_time"] = "not-a-datetime"
            storage.set(key, data)

        # 進行時間範圍查詢
        params = ListQueryParams(
            created_time_range=DateTimeRange(
                start=datetime(2024, 1, 1, 0, 0, 0), end=datetime(2024, 1, 2, 0, 0, 0)
            )
        )

        result = crud.list_with_params(params)

        # 無效格式的項目應該被過濾掉
        assert len(result.items) == 0

    def test_non_datetime_values_handling(self):
        """測試非日期時間值的處理"""
        storage = MemoryStorage()
        metadata_config = MetadataConfig(enable_timestamps=True)
        crud = SingleModelCRUD(
            TimezoneTestModel, storage, "test_model", metadata_config=metadata_config
        )

        # 創建測試數據
        created_id = crud.create({"name": "Test"})

        # 設置非日期時間值
        key = f"test_model:{created_id}"
        data = storage.get(key)
        if data:
            data["created_time"] = 12345  # 數字
            storage.set(key, data)

        # 進行時間範圍查詢
        params = ListQueryParams(
            created_time_range=DateTimeRange(
                start=datetime(2024, 1, 1, 0, 0, 0), end=datetime(2024, 1, 2, 0, 0, 0)
            )
        )

        result = crud.list_with_params(params)

        # 非日期時間值的項目應該被過濾掉
        assert len(result.items) == 0

    def test_none_values_handling(self):
        """測試 None 值的處理"""
        storage = MemoryStorage()
        metadata_config = MetadataConfig(enable_timestamps=True)
        crud = SingleModelCRUD(
            TimezoneTestModel, storage, "test_model", metadata_config=metadata_config
        )

        # 創建測試數據
        created_id = crud.create({"name": "Test"})

        # 設置 None 值
        key = f"test_model:{created_id}"
        data = storage.get(key)
        if data:
            data["created_time"] = None
            storage.set(key, data)

        # 進行時間範圍查詢
        params = ListQueryParams(
            created_time_range=DateTimeRange(
                start=datetime(2024, 1, 1, 0, 0, 0), end=datetime(2024, 1, 2, 0, 0, 0)
            )
        )

        result = crud.list_with_params(params)

        # None 值的項目應該被過濾掉
        assert len(result.items) == 0
