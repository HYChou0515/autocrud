"""測試 Schema Analyzer 對 TypedDict 預設值的處理"""

from typing import TypedDict
from autocrud.schema_analyzer import SchemaAnalyzer
from autocrud.metadata import MetadataConfig


class UserTypedDict(TypedDict):
    id: str
    name: str
    email: str
    age: int
    status: str


def test_schema_analyzer_with_defaults():
    """測試 Schema Analyzer 是否正確處理預設值"""

    # 測試沒有預設值的情況
    analyzer_no_defaults = SchemaAnalyzer(UserTypedDict, MetadataConfig())

    # 測試有預設值的情況
    analyzer_with_defaults = SchemaAnalyzer(
        UserTypedDict, MetadataConfig(), default_values={"status": "active", "age": 18}
    )

    # 檢查沒有預設值時的 optional 狀態
    print("沒有預設值時：")
    for field in ["id", "name", "email", "age", "status"]:
        is_optional = analyzer_no_defaults._is_optional_field(field)
        print(f"  {field}: optional = {is_optional}")

    print("\n有預設值時：")
    for field in ["id", "name", "email", "age", "status"]:
        is_optional = analyzer_with_defaults._is_optional_field(field)
        print(f"  {field}: optional = {is_optional}")

    # 驗證預設值讓相關欄位變成 optional
    assert not analyzer_no_defaults._is_optional_field("status")
    assert not analyzer_no_defaults._is_optional_field("age")

    assert analyzer_with_defaults._is_optional_field("status")
    assert analyzer_with_defaults._is_optional_field("age")

    # 沒有預設值的欄位應該保持不變
    assert not analyzer_with_defaults._is_optional_field("name")
    assert not analyzer_with_defaults._is_optional_field("email")


if __name__ == "__main__":
    test_schema_analyzer_with_defaults()
    print("\n✅ Schema Analyzer 預設值測試通過！")
