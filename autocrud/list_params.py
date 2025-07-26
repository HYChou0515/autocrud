"""列表查詢參數和結果類型定義"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class SortOrder(Enum):
    """排序順序"""

    ASC = "asc"  # 升序
    DESC = "desc"  # 降序


@dataclass
class DateTimeRange:
    """日期時間範圍"""

    start: Optional[datetime] = None
    end: Optional[datetime] = None

    def contains(self, value: datetime) -> bool:
        """檢查日期是否在範圍內"""
        if self.start and value < self.start:
            return False
        if self.end and value > self.end:
            return False
        return True


@dataclass
class ListQueryParams:
    """列表查詢參數"""

    # 分頁參數
    page: int = 1
    page_size: int = 20

    # 過濾參數
    created_by_filter: Optional[List[str]] = None  # 按創建者過濾
    updated_by_filter: Optional[List[str]] = None  # 按更新者過濾
    created_time_range: Optional[DateTimeRange] = None  # 創建時間範圍
    updated_time_range: Optional[DateTimeRange] = None  # 更新時間範圍

    # 排序參數
    sort_by: Optional[str] = None  # 排序字段 (created_time, updated_time, etc.)
    sort_order: SortOrder = SortOrder.DESC  # 排序順序

    def __post_init__(self):
        """驗證參數"""
        if self.page < 1:
            raise ValueError("page must be >= 1")
        if self.page_size < 1 or self.page_size > 1000:
            raise ValueError("page_size must be between 1 and 1000")


@dataclass
class ListResult:
    """列表查詢結果"""

    items: List[Dict[str, Any]]  # 項目列表
    total: int  # 總項目數
    page: int  # 當前頁碼
    page_size: int  # 每頁大小
    total_pages: int  # 總頁數
    has_next: bool  # 是否有下一頁
    has_prev: bool  # 是否有上一頁

    @classmethod
    def create(
        cls, items: List[Dict[str, Any]], total: int, params: ListQueryParams
    ) -> "ListResult":
        """創建列表結果"""
        total_pages = (total + params.page_size - 1) // params.page_size

        return cls(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
            total_pages=total_pages,
            has_next=params.page < total_pages,
            has_prev=params.page > 1,
        )
