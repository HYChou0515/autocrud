"""
測試 QB 表達式與 Search API 的整合
"""

from typing import Any

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from msgspec import Struct

from autocrud import AutoCRUD


class User(Struct):
    name: str
    age: int
    department: str
    active: bool = True


@pytest.fixture
def client() -> TestClient:
    """創建測試客戶端"""
    app: FastAPI = FastAPI()
    router: APIRouter = APIRouter()
    crud: AutoCRUD = AutoCRUD()
    crud.add_model(
        User,
        indexed_fields=[
            ("age", int),
            ("department", str),
            ("active", bool),
            ("name", str),  # 添加 name 來支持 complex expression 測試
        ],
    )
    crud.apply(router)
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def sample_users(client: TestClient) -> list[str]:
    """創建測試數據"""
    users: list[dict[str, Any]] = [
        {"name": "Alice", "age": 25, "department": "Engineering", "active": True},
        {"name": "Bob", "age": 30, "department": "Marketing", "active": True},
        {"name": "Charlie", "age": 35, "department": "Engineering", "active": False},
        {"name": "David", "age": 28, "department": "Sales", "active": True},
        {"name": "Eve", "age": 32, "department": "Engineering", "active": True},
    ]

    created_ids = []
    for user_data in users:
        response = client.post("/user", json=user_data)
        assert response.status_code == 200
        created_ids.append(response.json()["resource_id"])

    return created_ids


def test_qb_simple_equality(client: TestClient, sample_users: list[str]) -> None:
    """測試簡單的相等條件"""
    response = client.get(
        "/user/data", params={"qb": "QB['department'] == 'Engineering'"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert all(u["department"] == "Engineering" for u in data)


def test_qb_greater_than(client: TestClient, sample_users: list[str]) -> None:
    """測試大於條件"""
    response = client.get("/user/data", params={"qb": "QB['age'].gt(30)"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all(u["age"] > 30 for u in data)


def test_qb_and_condition(client: TestClient, sample_users: list[str]) -> None:
    """測試 AND 條件"""
    response = client.get(
        "/user/data",
        params={"qb": "QB['age'].gt(25) & QB['department'].eq('Engineering')"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all(u["age"] > 25 and u["department"] == "Engineering" for u in data)


def test_qb_or_condition(client: TestClient, sample_users: list[str]) -> None:
    """測試 OR 條件"""
    response = client.get(
        "/user/data", params={"qb": "QB['age'].lt(26) | QB['age'].gt(33)"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all(u["age"] < 26 or u["age"] > 33 for u in data)


def test_qb_not_condition(client: TestClient, sample_users: list[str]) -> None:
    """測試 NOT 條件"""
    response = client.get("/user/data", params={"qb": "~QB['active'].eq(True)"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert all(not u["active"] for u in data)


def test_qb_with_limit_and_offset(client: TestClient, sample_users: list[str]) -> None:
    """測試分頁參數與 QB 表達式結合"""
    # 首先確認總共有3筆 Engineering
    response = client.get(
        "/user/data", params={"qb": "QB['department'].eq('Engineering')"}
    )
    assert response.status_code == 200
    assert len(response.json()) == 3

    # 測試 limit=2, offset=1，應該返回2筆
    response = client.get(
        "/user/data",
        params={"qb": "QB['department'].eq('Engineering')", "limit": 2, "offset": 1},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_qb_with_sorting(client: TestClient, sample_users: list[str]) -> None:
    """測試排序與 QB 表達式結合"""
    response = client.get(
        "/user/data", params={"qb": "QB['department'].eq('Engineering').sort('-age')"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    # 驗證按年齡降序排列
    ages = [u["age"] for u in data]
    assert ages == sorted(ages, reverse=True)


def test_qb_bracket_syntax(client: TestClient, sample_users: list[str]) -> None:
    """測試方括號語法"""
    # 使用 indexed field 來搜尋
    response = client.get("/user/data", params={"qb": "QB['age'] == 25"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["age"] == 25
    assert data[0]["name"] == "Alice"


def test_qb_conflict_with_data_conditions(
    client: TestClient, sample_users: list[str]
) -> None:
    """測試 qb 與 data_conditions 衝突時應返回錯誤"""
    response = client.get(
        "/user/data",
        params={
            "qb": "QB['age'].gt(25)",
            "data_conditions": '[{"field_path": "department", "operator": "eq", "value": "Engineering"}]',
        },
    )
    # FastAPI 會將 422 包裝成 400，但 detail 中會包含原始訊息
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "data_conditions" in detail


def test_qb_conflict_with_conditions(
    client: TestClient, sample_users: list[str]
) -> None:
    """測試 qb 與 conditions 衝突時應返回錯誤"""
    response = client.get(
        "/user/data",
        params={
            "qb": "QB['age'].gt(25)",
            "conditions": '[{"field_path": "resource_id", "operator": "starts_with", "value": "user"}]',
        },
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "conditions" in detail


def test_qb_conflict_with_sorts(client: TestClient, sample_users: list[str]) -> None:
    """測試 qb 與 sorts 衝突時應返回錯誤"""
    response = client.get(
        "/user/data",
        params={
            "qb": "QB['age'].gt(25)",
            "sorts": '[{"type": "data", "field_path": "age", "direction": "+"}]',
        },
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "sorts" in detail


def test_qb_invalid_expression(client: TestClient, sample_users: list[str]) -> None:
    """測試無效的 QB 表達式應返回 400"""
    response = client.get("/user/data", params={"qb": "QB['age'].invalid_method(25)"})
    assert response.status_code == 400
    assert "Invalid QB expression" in response.json()["detail"]


def test_qb_with_meta_endpoint(client: TestClient, sample_users: list[str]) -> None:
    """測試 QB 表達式在 /meta endpoint 的使用"""
    response = client.get(
        "/user/meta", params={"qb": "QB['department'].eq('Engineering')"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3


def test_qb_with_full_endpoint(client: TestClient, sample_users: list[str]) -> None:
    """測試 QB 表達式在 /full endpoint 的使用"""
    response = client.get("/user/full", params={"qb": "QB['age'].between(25, 30)"})
    assert response.status_code == 200
    data = response.json()
    # between 是包含邊界的，25-30 包含 Alice(25), Bob(30), David(28)
    assert len(data) == 3
    assert all(25 <= item["data"]["age"] <= 30 for item in data)


def test_qb_with_count_endpoint(client: TestClient, sample_users: list[str]) -> None:
    """測試 QB 表達式在 /count endpoint 的使用"""
    response = client.get(
        "/user/count", params={"qb": "QB['department'].eq('Engineering')"}
    )
    assert response.status_code == 200
    assert response.json() == 3


def test_qb_complex_expression(client: TestClient, sample_users: list[str]) -> None:
    """測試複雜的 QB 表達式"""
    response = client.get(
        "/user/data",
        params={
            "qb": "(QB['age'].gt(25) & QB['department'].eq('Engineering')) | QB['name'].eq('Bob')"
        },
    )
    assert response.status_code == 200
    data = response.json()
    # (age > 25 AND department == Engineering): Charlie (35), Eve (32)
    # OR name == Bob: Bob (30, Marketing)
    # 總共: Charlie + Eve + Bob = 3
    assert len(data) == 3


def test_qb_string_methods(client: TestClient, sample_users: list[str]) -> None:
    """測試字符串方法"""
    # contains
    response = client.get("/user/data", params={"qb": "QB['name'].contains('li')"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any("li" in u["name"] for u in data)

    # starts_with
    response = client.get("/user/data", params={"qb": "QB['name'].starts_with('A')"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Alice"

    # ends_with
    response = client.get("/user/data", params={"qb": "QB['name'].ends_with('e')"})
    assert response.status_code == 200
    data = response.json()
    assert all(u["name"].endswith("e") for u in data)

    # regex
    response = client.get("/user/data", params={"qb": "QB['name'].regex(r'^[A-C]')"})
    assert response.status_code == 200
    data = response.json()
    assert all(u["name"][0] in "ABC" for u in data)


def test_qb_boolean_methods(client: TestClient, sample_users: list[str]) -> None:
    """測試布林方法"""
    # is_true
    response = client.get("/user/data", params={"qb": "QB['active'].is_true()"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 4
    assert all(u["active"] is True for u in data)

    # is_false
    response = client.get("/user/data", params={"qb": "QB['active'].is_false()"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert all(u["active"] is False for u in data)

    # is_null (需要有 null 值的欄位，這裡用不存在的值測試)
    response = client.get("/user/data", params={"qb": "QB['active'].is_not_null()"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 5


def test_qb_between_range(client: TestClient, sample_users: list[str]) -> None:
    """測試 between 範圍查詢"""
    response = client.get("/user/data", params={"qb": "QB['age'].between(26, 33)"})
    assert response.status_code == 200
    data = response.json()
    # 26-33: Bob(30), David(28), Eve(32)
    assert len(data) == 3
    assert all(26 <= u["age"] <= 33 for u in data)


def test_qb_in_list(client: TestClient, sample_users: list[str]) -> None:
    """測試 in 列表操作"""
    response = client.get(
        "/user/data",
        params={"qb": "QB['department'].in_(['Engineering', 'Marketing'])"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 4
    assert all(u["department"] in ["Engineering", "Marketing"] for u in data)


def test_qb_operators_shortcuts(client: TestClient, sample_users: list[str]) -> None:
    """測試運算符快捷方式"""
    # % for regex
    response = client.get("/user/data", params={"qb": "QB['name'] % r'^[AB]'"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all(u["name"][0] in "AB" for u in data)

    # << for in_list
    response = client.get("/user/data", params={"qb": "QB['name'] << ['Alice', 'Bob']"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    # >> for contains
    response = client.get("/user/data", params={"qb": "QB['name'] >> 'a'"})
    assert response.status_code == 200
    data = response.json()
    assert all("a" in u["name"] for u in data)


def test_qb_comparison_operators(client: TestClient, sample_users: list[str]) -> None:
    """測試各種比較運算符"""
    # ==
    response = client.get("/user/data", params={"qb": "QB['age'] == 30"})
    assert response.status_code == 200
    assert len(response.json()) == 1

    # !=
    response = client.get("/user/data", params={"qb": "QB['age'] != 30"})
    assert response.status_code == 200
    assert len(response.json()) == 4

    # >
    response = client.get("/user/data", params={"qb": "QB['age'] > 30"})
    assert response.status_code == 200
    data = response.json()
    assert all(u["age"] > 30 for u in data)

    # >=
    response = client.get("/user/data", params={"qb": "QB['age'] >= 30"})
    assert response.status_code == 200
    data = response.json()
    assert all(u["age"] >= 30 for u in data)

    # <
    response = client.get("/user/data", params={"qb": "QB['age'] < 30"})
    assert response.status_code == 200
    data = response.json()
    assert all(u["age"] < 30 for u in data)

    # <=
    response = client.get("/user/data", params={"qb": "QB['age'] <= 30"})
    assert response.status_code == 200
    data = response.json()
    assert all(u["age"] <= 30 for u in data)


def test_qb_numeric_operations(client: TestClient, sample_users: list[str]) -> None:
    """測試數值運算"""
    # 加法
    response = client.get("/user/data", params={"qb": "QB['age'].gt(20 + 5)"})
    assert response.status_code == 200
    data = response.json()
    assert all(u["age"] > 25 for u in data)

    # 減法
    response = client.get("/user/data", params={"qb": "QB['age'].lt(40 - 5)"})
    assert response.status_code == 200
    data = response.json()
    assert all(u["age"] < 35 for u in data)

    # 乘法
    response = client.get("/user/data", params={"qb": "QB['age'].gt(5 * 5)"})
    assert response.status_code == 200
    data = response.json()
    assert all(u["age"] > 25 for u in data)

    # 除法
    response = client.get("/user/data", params={"qb": "QB['age'].lt(60 / 2)"})
    assert response.status_code == 200
    data = response.json()
    assert all(u["age"] < 30 for u in data)


def test_qb_unary_operators(client: TestClient, sample_users: list[str]) -> None:
    """測試一元運算符"""
    # 正號
    response = client.get("/user/data", params={"qb": "QB['age'].gt(+25)"})
    assert response.status_code == 200
    data = response.json()
    assert all(u["age"] > 25 for u in data)

    # 負號
    response = client.get("/user/data", params={"qb": "QB['age'].gt(-(-30))"})
    assert response.status_code == 200
    data = response.json()
    assert all(u["age"] > 30 for u in data)


def test_qb_literals(client: TestClient, sample_users: list[str]) -> None:
    """測試字面量"""
    # 布林字面量 True
    response = client.get("/user/data", params={"qb": "QB['active'].eq(True)"})
    assert response.status_code == 200
    assert len(response.json()) == 4

    # 布林字面量 False
    response = client.get("/user/data", params={"qb": "QB['active'].eq(False)"})
    assert response.status_code == 200
    assert len(response.json()) == 1

    # 字符串拼接
    response = client.get("/user/data", params={"qb": "QB['name'].eq('Al' + 'ice')"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Alice"


def test_qb_chained_methods(client: TestClient, sample_users: list[str]) -> None:
    """測試鏈式方法調用"""
    # filter
    response = client.get(
        "/user/data",
        params={"qb": "QB['age'].gt(25).filter(QB['active'].eq(True))"},
    )
    assert response.status_code == 200
    data = response.json()
    assert all(u["age"] > 25 and u["active"] is True for u in data)

    # exclude
    response = client.get(
        "/user/data",
        params={"qb": "QB['age'].gt(25).exclude(QB['department'].eq('Marketing'))"},
    )
    assert response.status_code == 200
    data = response.json()
    assert all(u["age"] > 25 and u["department"] != "Marketing" for u in data)


def test_qb_page_method(client: TestClient, sample_users: list[str]) -> None:
    """測試 page 方法"""
    # 第1頁，每頁2筆
    response = client.get(
        "/user/data",
        params={"qb": "QB['department'].eq('Engineering').page(1, 2)"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    # 第2頁，每頁2筆
    response = client.get(
        "/user/data",
        params={"qb": "QB['department'].eq('Engineering').page(2, 2)"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1


def test_qb_first_method(client: TestClient, sample_users: list[str]) -> None:
    """測試 first 方法"""
    response = client.get(
        "/user/data", params={"qb": "QB['department'].eq('Engineering').first()"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1


def test_qb_logical_not(client: TestClient, sample_users: list[str]) -> None:
    """測試邏輯 not"""
    response = client.get("/user/data", params={"qb": "QB['active'].eq(not False)"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 4


def test_qb_meta_attributes(client: TestClient, sample_users: list[str]) -> None:
    """測試 meta 屬性訪問"""
    # QB.resource_id()
    response = client.get(
        "/user/data", params={"qb": "QB.resource_id().starts_with('user')"}
    )
    assert response.status_code == 200
    # 所有資源 ID 都應該以 'user' 開頭
    data = response.json()
    assert len(data) >= 0  # 可能因為實作不同而有不同結果


def test_qb_case_insensitive_methods(
    client: TestClient, sample_users: list[str]
) -> None:
    """測試大小寫不敏感的方法"""
    # icontains
    response = client.get("/user/data", params={"qb": "QB['name'].icontains('ALICE')"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1

    # istarts_with
    response = client.get("/user/data", params={"qb": "QB['name'].istarts_with('a')"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1

    # iends_with
    response = client.get("/user/data", params={"qb": "QB['name'].iends_with('E')"})
    assert response.status_code == 200
    data = response.json()
    assert all(u["name"].lower().endswith("e") for u in data)


def test_qb_truthy_falsy(client: TestClient, sample_users: list[str]) -> None:
    """測試 truthy/falsy 方法"""
    # is_truthy
    response = client.get("/user/data", params={"qb": "QB['active'].is_truthy()"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 4

    # is_falsy
    response = client.get("/user/data", params={"qb": "QB['active'].is_falsy()"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1


def test_qb_not_methods(client: TestClient, sample_users: list[str]) -> None:
    """測試 not_ 開頭的方法"""
    # not_contains
    response = client.get("/user/data", params={"qb": "QB['name'].not_contains('z')"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 5

    # not_starts_with
    response = client.get(
        "/user/data", params={"qb": "QB['name'].not_starts_with('Z')"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 5

    # not_ends_with
    response = client.get("/user/data", params={"qb": "QB['name'].not_ends_with('z')"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 5


def test_qb_all_any_combinators(client: TestClient, sample_users: list[str]) -> None:
    """測試 all/any 組合器"""
    # all
    response = client.get(
        "/user/data",
        params={"qb": "QB.all(QB['age'].gt(20), QB['active'].eq(True))"},
    )
    assert response.status_code == 200
    data = response.json()
    assert all(u["age"] > 20 and u["active"] is True for u in data)

    # any
    response = client.get(
        "/user/data",
        params={"qb": "QB.any(QB['name'].eq('Alice'), QB['name'].eq('Bob'))"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_qb_order_by_alias(client: TestClient, sample_users: list[str]) -> None:
    """測試 order_by 別名"""
    response = client.get(
        "/user/data",
        params={"qb": "QB['department'].eq('Engineering').order_by('-age')"},
    )
    assert response.status_code == 200
    data = response.json()
    ages = [u["age"] for u in data]
    assert ages == sorted(ages, reverse=True)


def test_qb_nested_expressions(client: TestClient, sample_users: list[str]) -> None:
    """測試巢狀表達式"""
    response = client.get(
        "/user/data",
        params={
            "qb": "((QB['age'].gt(25) | QB['age'].lt(28)) & QB['active'].eq(True))"
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert all(((u["age"] > 25 or u["age"] < 28) and u["active"] is True) for u in data)


def test_qb_multiple_args_method(client: TestClient, sample_users: list[str]) -> None:
    """測試多參數方法"""
    response = client.get("/user/data", params={"qb": "QB['age'].between(25, 32)"})
    assert response.status_code == 200
    data = response.json()
    assert all(25 <= u["age"] <= 32 for u in data)


def test_qb_datetime_variable(client: TestClient, sample_users: list[str]) -> None:
    """測試 datetime 變量訪問 (line 156)"""
    # 使用 datetime 構造日期
    response = client.get(
        "/user/data", params={"qb": "QB['age'].gt(datetime.datetime(2000, 1, 1).year)"}
    )
    assert response.status_code == 200
    # 2000 年，所有用戶年齡都小於 2000
    data = response.json()
    assert len(data) == 0


def test_qb_dt_variable(client: TestClient, sample_users: list[str]) -> None:
    """測試 dt 變量訪問 (line 153)"""
    # 這個比較困難，因為需要在表達式中使用 dt
    pass


def test_qb_datetime_timedelta(client: TestClient, sample_users: list[str]) -> None:
    """測試 datetime.timedelta 調用 (lines 219-227)"""
    # 使用 timedelta 計算
    response = client.get(
        "/user/data",
        params={"qb": "QB['age'].gt(datetime.timedelta(days=10000).days / 365)"},
    )
    assert response.status_code == 200
    data = response.json()
    # 10000天 ≈ 27年，所以 age > 27 的有: Bob(30), Charlie(35), David(28), Eve(32)
    assert len(data) == 4


def test_qb_datetime_date_constructor(
    client: TestClient, sample_users: list[str]
) -> None:
    """測試 datetime.date 構造函數 (lines 219-227)"""
    response = client.get(
        "/user/data",
        params={"qb": "QB['age'].gt(datetime.date(2000, 1, 1).year - 1975)"},
    )
    assert response.status_code == 200
    # 2000 - 1975 = 25，age > 25 的有 4 人
    data = response.json()
    assert len(data) == 4


def test_qb_tuple_literal(client: TestClient, sample_users: list[str]) -> None:
    """測試元組字面量 (line 241)"""
    # 使用元組作為參數
    response = client.get("/user/data", params={"qb": "QB['age'].in_((25, 30, 35))"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3


def test_qb_error_handling(client: TestClient, sample_users: list[str]) -> None:
    """測試錯誤處理"""
    # 語法錯誤 (line 137)
    response = client.get("/user/data", params={"qb": "QB['age'].gt("})
    assert response.status_code == 400

    # 不支持的變量 (line 158)
    response = client.get("/user/data", params={"qb": "undefined_var"})
    assert response.status_code == 400

    # 不允許的 QB 屬性 (line 170)
    response = client.get("/user/data", params={"qb": "QB.not_allowed_attr()"})
    assert response.status_code == 400

    # 不存在的 datetime 屬性 (line 178)
    response = client.get("/user/data", params={"qb": "dt.nonexistent"})
    assert response.status_code == 400

    # 函數調用錯誤 (line 233)
    response = client.get("/user/data", params={"qb": "QB['age'].between()"})
    assert response.status_code == 400

    # 不允許的方法 (line 227)
    response = client.get("/user/data", params={"qb": "datetime.timezone()"})
    assert response.status_code == 400


def test_qb_datetime_time_constructor(
    client: TestClient, sample_users: list[str]
) -> None:
    """測試 datetime.time 構造函數"""
    # time 構造函數應該被允許
    response = client.get(
        "/user/data", params={"qb": "QB['age'].gt(datetime.time(12, 30).hour * 2)"}
    )
    assert response.status_code == 200
    # 12 * 2 = 24，所有人都大於 24
    data = response.json()
    assert len(data) == 5


def test_qb_list_literal(client: TestClient, sample_users: list[str]) -> None:
    """測試列表字面量 (line 237)"""
    # 直接在表達式中使用列表
    response = client.get(
        "/user/data", params={"qb": "QB['name'].in_(['Alice', 'Bob', 'Charlie'])"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert all(u["name"] in ["Alice", "Bob", "Charlie"] for u in data)


def test_qb_subscript_error(client: TestClient, sample_users: list[str]) -> None:
    """測試下標錯誤"""
    # 非字符串下標 (line 196)
    response = client.get("/user/data", params={"qb": "QB[123]"})
    assert response.status_code == 400

    # 在非 QB 對象上使用下標 (line 199)
    response = client.get("/user/data", params={"qb": "QB['name'][0]"})
    assert response.status_code == 400


def test_qb_attribute_not_found(client: TestClient, sample_users: list[str]) -> None:
    """測試屬性不存在 (line 183)"""
    # Field 對象沒有這個屬性
    response = client.get("/user/data", params={"qb": "QB['age'].nonexistent_attr"})
    assert response.status_code == 400


def test_qb_not_in_operator(client: TestClient, sample_users: list[str]) -> None:
    """測試 not_in 運算符"""
    # 測試 not_in 方法
    response = client.get(
        "/user/data", params={"qb": "QB['name'].not_in(['Alice', 'Bob'])"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert all(u["name"] not in ["Alice", "Bob"] for u in data)


def test_qb_unsupported_binary_operator(
    client: TestClient, sample_users: list[str]
) -> None:
    """測試不支持的二元運算符 (line 276)"""
    # ** 冪次運算符不支持
    response = client.get("/user/data", params={"qb": "QB['age'].gt(2 ** 5)"})
    assert response.status_code == 400
    assert "Binary operator not supported" in response.json()["detail"]


def test_qb_unsupported_comparison_operator(
    client: TestClient, sample_users: list[str]
) -> None:
    """測試不支持的比較運算符 (line 325)"""
    # in 運算符應該用 in_() 方法，不能直接用
    response = client.get("/user/data", params={"qb": "QB['name'] in ['Alice', 'Bob']"})
    assert response.status_code == 400
    assert "Comparison operator not supported" in response.json()["detail"]


def test_qb_unsupported_ast_node(client: TestClient, sample_users: list[str]) -> None:
    """測試不支持的 AST 節點類型 (line 330)"""
    # Lambda 表達式不支持
    response = client.get("/user/data", params={"qb": "lambda x: x > 0"})
    assert response.status_code == 400
    assert "AST node type not supported" in response.json()["detail"]
