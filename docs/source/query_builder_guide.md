# 🔍 Query Builder 完整指南

---

## 簡介
```{versionadded} 0.7.5
```

AutoCRUD Query Builder 提供了一個 Pythonic 的 API 來建構資源查詢條件。它支援：

- 🔍 豐富的查詢運算符（`==`, `>`, `<<`, `>>` 等）
- 🔗 直觀的鏈式語法
- 📅 便捷的日期時間查詢
- 🎯 型別安全的欄位引用
- ⚡ 高效的查詢執行

## 快速開始

```python
from autocrud.query import QB

# 簡單查詢
query = QB["age"] > 18

# 組合條件
query = (QB["age"] > 18) & (QB["department"] == "Engineering")

# 使用 ResourceManager 執行查詢
results = resource_manager.search_resources(query)
```

## 基本概念

### QB (Query Builder)

`QB` 是查詢建構器的入口點，使用方括號語法存取欄位：

```python
from autocrud.query import QB

# 存取欄位
age_field = QB["age"]
name_field = QB["name"]
email_field = QB["email"]

# 支援特殊字元和點號
dotted_field = QB["user.profile.bio"]
special_field = QB["field-with-dashes"]
```

### Field 物件

每個 `QB["field_name"]` 返回一個 `Field` 物件，提供各種查詢方法：

```python
field = QB["age"]
condition = field.gt(18)  # 大於 18

# Field 可以直接使用，等同於 is_truthy()
QB["verified"]  # 檢查 verified 有真值
QB["email"] & QB["verified"]  # 有 email 且已驗證
~QB["deleted"]  # 檢查 deleted 是空值或假值
```

### ConditionBuilder

查詢條件返回 `ConditionBuilder` 物件，可以組合和鏈接：

```python
cond1 = QB["age"] > 18
cond2 = QB["age"] < 65
combined = cond1 & cond2  # AND 組合
```

---

## 欄位操作

### 基本存取

```python
# 使用方括號
QB["field_name"]
```
---

## API 參考快查

### [比較運算符](#comparison-operators)

| 方法 | 運算符 | 說明 |
|------|--------|------|
| `eq(value)` | `==` | 等於 |
| `ne(value)` | `!=` | 不等於 |
| `gt(value)` | `>` | 大於 |
| `gte(value)` | `>=` | 大於等於 |
| `lt(value)` | `<` | 小於 |
| `lte(value)` | `<=` | 小於等於 |
| `in_(values)` <br> `one_of(values)` | `<<` | 包含於列表 |
| `not_in(values)` | - | 不包含於列表 |
| `between(min, max)` <br> `in_range(min, max)` | - | 介於範圍 |

### [字串方法](#string-queries)

| 方法 | 運算符 | 說明 |
|------|--------|------|
| `contains(s)` | `>>` | 包含子字串 |
| `icontains(s)` | - | 包含子字串（不分大小寫） |
| `starts_with(s)` | - | 開始於 |
| `istarts_with(s)` | - | 開始於（不分大小寫） |
| `ends_with(s)` | - | 結束於 |
| `iends_with(s)` | - | 結束於（不分大小寫） |
| `not_contains(s)` | - | 不包含 |
| `not_starts_with(s)` | - | 不開始於 |
| `not_ends_with(s)` | - | 不結束於 |
| `regex(pattern)` <br> `match(pattern)` | - | 正則匹配 |
| `like(pattern)` | - | SQL LIKE 模式 |
| `is_empty()` | - | 空字串或 NULL |
| `is_blank()` | - | 空白（含空白字元） |

### [布林方法](#boolean-queries)

| 方法 | 運算符 | 說明 |
|------|--------|------|
| `is_true()` | - | 等於 True |
| `is_false()` | - | 等於 False |
| `is_truthy()` | 直接使用 | 有意義的值（非 None/False/0/""/[]） |
| `is_falsy()` | `~` | 空值或假值 |

### [NULL 處理](#null-handling)

| 方法 | 運算符 | 說明 |
|------|--------|------|
| `is_null(True)` | - | 是 NULL |
| `is_null(False)` <br> `is_not_null()` <br> `has_value()` | - | 不是 NULL |
| `exists(True)` | - | 欄位存在 |
| `exists(False)` | - | 欄位不存在 |
| `isna(True)` | - | 不可用（不存在或 NULL） |
| `isna(False)` | - | 可用 |

### [日期時間方法](#datetime-queries)

| 方法 | 說明 |
|------|------|
| `today(tz=None)` | 今天 |
| `yesterday(tz=None)` | 昨天 |
| `this_week(start_day=0, tz=None)` | 本週 |
| `this_month(tz=None)` | 本月 |
| `this_year(tz=None)` | 今年 |
| `last_n_days(n, tz=None)` | 最近 N 天 |

### [轉換方法](#field-transforms)

| 方法 | 說明 |
|------|------|
| `length()` | 取得長度（字串或陣列） |

### [排序方法](#sorting)

| 方法 | 說明 |
|------|------|
| `sort(*sorts)` <br> `order_by(*sorts)` | 排序 |
| `asc()` | 升序 |
| `desc()` | 降序 |

### [分頁方法](#pagination)

| 方法 | 說明 |
|------|------|
| `limit(n)` | 限制數量 |
| `offset(n)` | 偏移量 |
| `page(n, size=10)` | 頁碼分頁 |
| `first()` | 第一筆 |

### [邏輯組合](#logical-operations)

| 方法/運算符 | 說明 |
|-------------|------|
| `&` | AND 運算 |
| `\|` | OR 運算 |
| `~` | NOT 運算 |
| `QB.all(*conds)` | 所有條件 AND |
| `QB.any(*conds)` | 任一條件 OR |
| `filter(*conds)` | 篩選（AND） |
| `exclude(*conds)` | 排除（NOT OR） |

---

<a id="comparison-operators"></a>
## 比較運算符

### 等於 / 不等於

```python
# 等於
QB["status"] == "active"
QB["status"].eq("active")

# 範例：查詢狀態為 active 的資源
active_resources = manager.search_resources(QB["status"] == "active")

# 不等於
QB["status"] != "deleted"
QB["status"].ne("deleted")

# 範例：查詢未刪除的用戶
not_deleted = manager.search_resources(QB["status"] != "deleted")
```

### 大於 / 小於

```python
# 大於
QB["age"] > 18
QB["age"].gt(18)

# 範例：查詢成年用戶
adults = manager.search_resources(QB["age"] > 18)

# 大於等於
QB["age"] >= 18
QB["age"].gte(18)

# 小於
QB["price"] < 100
QB["price"].lt(100)

# 範例：查詢低價商品
cheap_items = manager.search_resources(QB["price"] < 100)

# 小於等於
QB["price"] <= 100
QB["price"].lte(100)
```

### 包含 / 排除

```python
# 檢查值是否在列表中
QB["status"].in_(["active", "pending", "approved"])
QB["status"].one_of(["active", "pending"])  # 別名
QB["status"] << ["active", "pending", "approved"]  # << 運算符別名

# 範例：查詢多種狀態的訂單
orders = manager.search_resources(
    QB["status"] << ["pending", "processing", "shipped"]
)

# 檢查值不在列表中
QB["status"].not_in(["deleted", "banned"])

# 範例：排除已刪除或封禁的用戶
valid_users = manager.search_resources(
    QB["status"].not_in(["deleted", "banned"])
)
```

---

<a id="logical-operations"></a>
## 邏輯運算

### AND 運算

```python
# 使用 & 運算符
query = (QB["age"] > 18) & (QB["age"] < 65)

# 範例：查詢工作年齡的用戶
working_age = manager.search_resources(
    (QB["age"] >= 18) & (QB["age"] <= 65)
)

# 使用 QB.all()
query = QB.all(
    QB["age"] > 18,
    QB["age"] < 65,
    QB["status"] == "active"
)

# 範例：活躍的成年工程師
active_engineers = manager.search_resources(
    QB.all(
        QB["age"] >= 18,
        QB["status"] == "active",
        QB["department"] == "Engineering"
    )
)

# QB.all() 無參數 - 查詢所有資源
all_resources = manager.search_resources(QB.all())

# 使用 filter() 方法
query = QB.filter(
    QB["age"] > 18,
    QB["status"] == "active"
)
```

### OR 運算

```python
# 使用 | 運算符
query = (QB["department"] == "Engineering") | (QB["department"] == "Sales")

# 範例：查詢技術或銷售部門的員工
tech_or_sales = manager.search_resources(
    (QB["department"] == "Engineering") | (QB["department"] == "Sales")
)

# 使用 QB.any()
query = QB.any(
    QB["department"] == "Engineering",
    QB["department"] == "Sales",
    QB["department"] == "Marketing"
)
# 注意：QB.any() 必須至少提供一個條件，空參數會拋出 ValueError

# 範例：多部門篩選
multi_dept = manager.search_resources(
    QB.any(
        QB["department"] == "Engineering",
        QB["department"] == "Sales",
        QB["department"] == "Marketing"
    )
)
```

### NOT 運算

```python
# 使用 ~ 運算符
query = ~(QB["status"] == "deleted")

# 使用 exclude() 方法
query = QB.exclude(
    QB["status"] == "deleted",
    QB["is_banned"] == True
)
```

### 複雜組合

```python
# 括號控制優先級
query = (
    (QB["age"] > 18) & (QB["age"] < 65)
) | (
    QB["is_premium"] == True
)

# 等同於 SQL:
# WHERE (age > 18 AND age < 65) OR is_premium = true
```

---

<a id="string-queries"></a>
## 字串查詢

### 包含 / 開始 / 結束

```python
# 包含子字串
QB["name"].contains("John")
QB["name"] >> "John"  # >> 運算符別名
QB["description"].contains("urgent")

# 範例：搜尋名字包含 "王" 的用戶
wang_users = manager.search_resources(QB["name"] >> "王")

# 範例：搜尋描述包含 "緊急" 的任務
urgent_tasks = manager.search_resources(
    QB["description"].contains("緊急")
)

# 開始於
QB["email"].starts_with("admin")
QB["code"].starts_with("PRE-")

# 範例：查詢管理員帳號
admins = manager.search_resources(
    QB["email"].starts_with("admin")
)

# 結束於
QB["email"].ends_with("@gmail.com")
QB["filename"].ends_with(".pdf")

# 範例：查詢 Gmail 用戶
gmail_users = manager.search_resources(
    QB["email"].ends_with("@gmail.com")
)
```

### 大小寫不敏感

```python
# 不分大小寫包含
QB["name"].icontains("john")  # 匹配 "John", "JOHN", "john"

# 不分大小寫開始
QB["email"].istarts_with("admin")  # 匹配 "Admin@", "ADMIN@"

# 不分大小寫結束
QB["filename"].iends_with(".pdf")  # 匹配 ".PDF", ".Pdf"
```

### 否定查詢

```python
# 不包含
QB["description"].not_contains("spam")

# 不開始於
QB["email"].not_starts_with("test")

# 不結束於
QB["filename"].not_ends_with(".tmp")
```

### 正則表達式

```python
# 使用正則表達式
QB["email"].regex(r".*@gmail\.com$")
QB["phone"].regex(r"^\+886-\d{9}$")
QB["code"].match(r"^[A-Z]{3}-\d{4}$")  # match() 是 regex() 的別名
```

### SQL LIKE 模式

```python
# % 表示任意字元，_ 表示單一字元
QB["name"].like("A%")           # 開始於 A
QB["email"].like("%@gmail.com") # 結束於 @gmail.com
QB["code"].like("A_C")          # 匹配 ABC, A1C 等
QB["desc"].like("%urgent%")     # 包含 urgent
```

### 空值檢查

```python
# 空字串或 null
QB["description"].is_empty()

# 空白（空字串、null 或只有空白字元）
QB["comment"].is_blank()  # 匹配 "", null, "  ", "\t\n"
```

---

## 數值與範圍查詢

### 範圍查詢

```python
# 介於（包含邊界）
QB["age"].between(18, 65)
QB["price"].in_range(100, 1000)  # 別名

# 範例：查詢特定年齡範圍的用戶
working_age = manager.search_resources(QB["age"].between(18, 65))

# 範例：查詢中等價位商品
mid_range = manager.search_resources(
    QB["price"].between(1000, 5000)
)

# 手動組合
(QB["age"] >= 18) & (QB["age"] <= 65)
```

### 數學運算

```python
# 基本比較
QB["quantity"] > 0
QB["balance"] >= 1000
QB["discount"] <= 0.5

# 組合條件
(QB["price"] > 100) & (QB["price"] < 1000)
```

---

<a id="datetime-queries"></a>
## 日期時間查詢

### 今天

```python
# 今天（預設本地時區）
QB.created_time.today()

# 指定時區（UTC+8）
QB.created_time.today(tz=8)
QB.created_time.today(tz="+8")

# 使用 ZoneInfo
from zoneinfo import ZoneInfo
QB.created_time.today(tz=ZoneInfo("Asia/Taipei"))
```

### 昨天

```python
QB.created_time.yesterday()
QB.updated_time.yesterday(tz=8)
```

### 本週

```python
# 本週（預設週一開始）
QB.created_time.this_week()

# 指定週起始日（0=週一, 6=週日）
QB.created_time.this_week(start_day=6)  # 週日開始

# 指定時區
QB.created_time.this_week(tz=8)
```

### 本月

```python
QB.created_time.this_month()
QB.created_time.this_month(tz=8)
```

### 今年

```python
QB.created_time.this_year()
QB.created_time.this_year(tz=8)
```

### 最近 N 天

```python
# 最近 7 天
QB.created_time.last_n_days(7)

# 最近 30 天
QB.created_time.last_n_days(30, tz=8)
```

### 日期範圍

```python
import datetime as dt

start = dt.datetime(2024, 1, 1)
end = dt.datetime(2024, 12, 31)

QB.created_time.between(start, end)
```

### 組合日期查詢

```python
# 今天創建且本週更新
query = QB.created_time.today() & QB.updated_time.this_week()

# 最近 7 天創建或今天更新
query = QB.created_time.last_n_days(7) | QB.updated_time.today()
```

---

<a id="boolean-queries"></a>
## 布林值查詢

### True / False

```python
# 等於 True
QB["is_active"].is_true()
QB["is_active"] == True

# 等於 False
QB["is_deleted"].is_false()
QB["is_deleted"] == False
```

### Truthy / Falsy

```python
# Truthy（有意義的值）
# 排除: None, False, 0, "", []
QB["status"].is_truthy()
QB["status"]  # 直接使用 Field 等同於 is_truthy()

# 範例：查詢有狀態值的資源
with_status = manager.search_resources(QB["status"])  # 簡潔寫法！

# Falsy（空值或假值）
# 匹配: None, False, 0, "", []
QB["comment"].is_falsy()
~QB["comment"]  # ~ 運算符別名

# 範例：查詢沒有備註的任務
no_comment = manager.search_resources(~QB["comment"])

# 範例：查詢空標籤或無標籤的文章
empty_tags = manager.search_resources(~QB["tags"])

# 組合使用
query = QB["verified"] & QB["email"]  # 已驗證且有 email
query = (QB["status"] == "active") & ~QB["comment"]  # 活躍且沒有備註
```

### 範例

```python
# 活躍且有標籤的用戶（使用運算符）
query = (QB["is_active"] == True) & QB["tags"]  # tags.is_truthy()

# 沒有備註的活躍任務
query = (QB["status"] == "active") & ~QB["comment"]

# 已驗證、有 email、未刪除的用戶
query = QB["verified"] & QB["email"] & ~QB["deleted_at"]

# 已刪除或被封禁的用戶
query = QB["is_deleted"].is_true() | QB["is_banned"].is_true()
```

---

<a id="field-transforms"></a>
## 欄位轉換

### 長度查詢

```python
# 使用 .length() 方法
QB["name"].length() > 5
QB["tags"].length() == 0
QB["email"].length().between(10, 50)

# 範例：查詢名字長度適中的用戶
moderate_name = manager.search_resources(
    QB["name"].length().between(3, 20)
)
```

### 字串長度

```python
# 名字長度超過 5 個字元
QB["name"].length() > 5

# 描述長度在 100-500 之間
QB["description"].length().between(100, 500)

# 範例：查詢有詳細描述的商品
detailed = manager.search_resources(
    QB["description"].length() > 100
)

# 郵件地址至少 10 個字元
QB["email"].length() >= 10
```

### 陣列/列表長度

```python
# 有超過 3 個標籤
QB["tags"].length() > 3

# 沒有標籤（空列表）
QB["tags"].length() == 0

# 範例：查詢有標籤的文章
tagged_articles = manager.search_resources(
    QB["tags"].length() > 0
)

# 至少有 1 個項目
QB["items"].length() >= 1
```

### 組合長度查詢

```python
# 名字長度適中且有標籤
query = (QB["name"].length().between(3, 20)) & (QB["tags"].length() > 0)

# 範例：查詢名字合理且有分類的商品
valid_products = manager.search_resources(
    (QB["name"].length().between(5, 50)) & (QB["categories"].length() > 0)
)

# 描述為空或很短
query = (QB["description"].length() == 0) | (QB["description"].length() < 10)
```

---

<a id="null-handling"></a>
## NULL 與空值處理

### NULL 檢查

```python
# 是 NULL
QB["deleted_at"].is_null()
QB["deleted_at"].is_null(True)

# 範例：查詢未刪除的資源
active = manager.search_resources(QB["deleted_at"].is_null())

# 不是 NULL
QB["deleted_at"].is_null(False)
QB["email"].is_not_null()  # 別名
QB["email"].has_value()     # 別名

# 範例：查詢有 email 的用戶
with_email = manager.search_resources(QB["email"].is_not_null())
```

### 欄位存在性

```python
# 欄位存在（即使值為 NULL）
QB["optional_field"].exists()
QB["optional_field"].exists(True)

# 欄位不存在
QB["optional_field"].exists(False)
```

### Is NA (Not Available)

```python
# 不可用（不存在或為 NULL）
QB["archived_at"].isna()
QB["archived_at"].isna(True)

# 範例：查詢沒有備註的任務
no_comment = manager.search_resources(QB["comment"].isna())

# 可用（存在且不為 NULL）
QB["archived_at"].isna(False)

# 範例：查詢已歸檔的資源
archived = manager.search_resources(QB["archived_at"].isna(False))
```

### 差異說明

```python
# is_null: 欄位存在但值為 NULL
QB["field"].is_null(True)   # field exists AND field = NULL

# exists: 欄位是否存在（不管值）
QB["field"].exists(True)    # field exists (value can be anything including NULL)

# isna: 欄位不存在或為 NULL
QB["field"].isna(True)      # field NOT exists OR field = NULL
```

---

<a id="sorting"></a>
## 排序

### 基本排序

```python
# 升序
query = QB["age"] > 18
query = query.sort(QB["age"].asc())

# 降序
query = query.sort(QB["age"].desc())
```

### 字串排序語法

```python
# 使用字串（預設升序）
query.sort("age")           # 升序
query.sort("+age")          # 明確指定升序
query.sort("-age")          # 降序

# 別名 order_by
query.order_by("-created_time")
```

### 多欄位排序

```python
# 先按部門升序，再按年齡降序
query.sort(
    QB["department"].asc(),
    QB["age"].desc()
)

# 使用字串語法
query.sort("department", "-age")
```

### Meta 欄位排序

```python
# 按創建時間降序
query.sort(QB.created_time.desc())

# 按更新時間升序
query.sort(QB.updated_time.asc())

# 組合排序
query.sort(
    QB.created_time.desc(),  # Meta 欄位
    QB["name"].asc()         # Data 欄位
)
```

---

<a id="pagination"></a>
## 分頁

### Limit 和 Offset

```python
# 限制數量
query = QB["status"] == "active"
query = query.limit(10)

# 偏移量
query = query.offset(20)

# 組合使用（第 3 頁，每頁 10 筆）
query.limit(10).offset(20)
```

### 頁碼分頁

```python
# 第 1 頁（每頁 10 筆，預設）
query.page(1)

# 第 2 頁，每頁 20 筆
query.page(2, size=20)

# 自訂頁面大小
query.page(3, size=50)
```

### First 方法

```python
# 只取第一筆
query = QB["email"] == "admin@example.com"
query = query.first()  # 等同於 limit(1)
```

### 分頁計算

```python
# page(n, size=s) 等同於:
# limit(s).offset((n-1) * s)

query.page(1, size=10)  # limit(10).offset(0)
query.page(2, size=10)  # limit(10).offset(10)
query.page(3, size=10)  # limit(10).offset(20)
```

---

## 組合查詢

### 複雜 AND/OR 組合

```python
# (A AND B) OR (C AND D)
query = (
    (QB["age"] > 18) & (QB["department"] == "Engineering")
) | (
    (QB["is_premium"] == True) & (QB["status"] == "active")
)
```

### 使用輔助方法

```python
# QB.all() - 所有條件都要滿足
query = QB.all(
    QB["age"] > 18,
    QB["age"] < 65,
    QB["status"] == "active",
    QB["is_verified"] == True
)

# QB.all() 無參數 - 查詢所有資源（無條件）
query = QB.all()  # 等同於不加任何條件

# QB.any() - 任一條件滿足即可
query = QB.any(
    QB["role"] == "admin",
    QB["role"] == "moderator",
    QB["role"] == "manager"
)
# 注意：QB.any() 必須至少提供一個條件，否則會拋出 ValueError
```

### Filter 和 Exclude

```python
# Filter - 包含符合條件的
query = QB.filter(
    QB["age"] > 18,
    QB["status"] == "active"
)
# 等同於: (age > 18) AND (status = 'active')

# Exclude - 排除符合條件的
query = QB.exclude(
    QB["is_deleted"] == True,
    QB["is_banned"] == True
)
# 等同於: NOT (is_deleted = true OR is_banned = true)
```

### 實際範例

```python
# 查詢活躍的成年工程師或管理員
query = QB.filter(
    QB["status"] == "active",
    QB["age"] >= 18
) & QB.any(
    QB["department"] == "Engineering",
    QB["role"] == "admin"
)

# 排除已刪除和被封禁的用戶
query = QB["status"] == "active"
query = query.exclude(
    QB["is_deleted"] == True,
    QB["is_banned"] == True
)
```

---

## Meta 欄位查詢

### 可用的 Meta 欄位

```python
QB.resource_id          # 資源 ID
QB.created_time         # 創建時間
QB.updated_time         # 更新時間
QB.created_by           # 創建者
QB.updated_by           # 更新者
QB.is_deleted           # 是否已刪除
QB.current_revision_id  # 當前版本 ID
QB.total_revision_count # 總版本數
```

### Meta 欄位查詢範例

```python
# 特定用戶創建的資源
QB.created_by == "user123"

# 今天更新的資源
QB.updated_time.today()

# 未刪除的資源
QB.is_deleted == False

# 有多個版本的資源
QB.total_revision_count > 1

# 特定資源 ID
QB.resource_id.in_(["id1", "id2", "id3"])
```

### 組合 Meta 和 Data 查詢

```python
# 今天創建的活躍用戶
query = QB.created_time.today() & (QB["status"] == "active")

# 本週更新且未刪除的資源
query = QB.updated_time.this_week() & (QB.is_deleted == False)

# 特定用戶創建的工程部門資源
query = (QB.created_by == "user123") & (QB["department"] == "Engineering")
```

---

## 進階技巧

### 動態查詢建構

```python
# 根據條件動態建構查詢
conditions = []

if age_min is not None:
    conditions.append(QB["age"] >= age_min)

if age_max is not None:
    conditions.append(QB["age"] <= age_max)

if department:
    conditions.append(QB["department"] == department)

# 組合所有條件
if conditions:
    query = QB.all(*conditions)
else:
    query = QB.all()  # 無條件查詢（匹配所有資源）
```

### 查詢重用

```python
# 定義基礎查詢
active_users = QB["status"] == "active"

# 在基礎查詢上添加條件
adult_active_users = active_users & (QB["age"] >= 18)
premium_active_users = active_users & (QB["is_premium"] == True)

# 多次使用
results1 = resource_manager.search_resources(adult_active_users)
results2 = resource_manager.search_resources(premium_active_users)
```

### 查詢轉換

```python
# 建構查詢
query = QB["age"] > 18
query = query.sort("-created_time")
query = query.limit(10)

# 轉換為 ResourceMetaSearchQuery
search_query = query.build()

# 直接傳給 ResourceManager
results = resource_manager.search_resources(query)
```

### 欄位名稱變數

```python
# 使用變數存儲欄位名稱
field_name = "email"
domain = "@gmail.com"

query = QB[field_name].ends_with(domain)

# 動態欄位查詢
def search_by_field(field_name, value):
    return QB[field_name] == value

query = search_by_field("status", "active")
```

### 常見查詢模式

```python
# 1. 分頁查詢模式
def get_page(page_num, page_size=20, filters=None):
    query = filters if filters else QB.all()
    return query.page(page_num, size=page_size)

# 2. 搜尋模式（多欄位 OR）
def search_users(keyword):
    return QB.any(
        QB["name"].icontains(keyword),
        QB["email"].icontains(keyword),
        QB["username"].icontains(keyword)
    )

# 3. 時間範圍篩選
def created_between(start, end):
    return QB.created_time.between(start, end)

# 4. 狀態篩選
def active_resources():
    return QB.all(
        QB["status"] == "active",
        QB.is_deleted == False
    )
```

### 效能最佳化提示

```python
# ✅ 好：使用索引欄位
query = QB["indexed_field"] == "value"

# ✅ 好：使用 in_ 代替多個 OR
query = QB["status"].in_(["active", "pending", "approved"])

# ❌ 避免：過度複雜的正則表達式
query = QB["field"].regex(r"^(?=.*[A-Z])(?=.*[0-9])(?=.*[@#$%]).{8,}$")

# ✅ 好：將常用查詢條件移到前面
query = (QB["status"] == "active") & (QB["complex_field"].regex("..."))
```

---

## 完整範例

### 電商產品查詢

```python
from autocrud.query import QB

# 價格在 100-1000 之間的活躍產品，且有至少 3 個標籤
query = QB.all(
    QB["price"].between(100, 1000),
    QB["status"] == "active",
    QB["tags"].length() >= 3
)

# 按價格升序排列，取前 20 筆
query = query.sort("price").limit(20)

results = product_manager.search_resources(query)
```

### 用戶管理查詢

```python
# 活躍的成年用戶，且最近 30 天內有活動
query = QB.all(
    QB["status"] == "active",
    QB["age"] >= 18,
    QB.updated_time.last_n_days(30)
)

# 排除已刪除和被封禁的
query = query.exclude(
    QB["is_deleted"] == True,
    QB["is_banned"] == True
)

# 按最後活動時間降序
query = query.sort(QB.updated_time.desc())

results = user_manager.search_resources(query)
```

### 內容搜尋查詢

```python
# 搜尋標題或內容包含關鍵字的文章
keyword = "Python"

query = QB.any(
    QB["title"].icontains(keyword),
    QB["content"].icontains(keyword),
    QB["tags"].contains(keyword.lower())
)

# 只搜尋已發布的文章
query = query & (QB["status"] == "published")

# 按相關度（更新時間）降序
query = query.sort(QB.updated_time.desc()).limit(50)

results = article_manager.search_resources(query)
```

### 報表統計查詢

```python
# 本月創建的訂單
this_month_orders = QB.created_time.this_month()

# 已完成的訂單
completed_orders = QB["status"] == "completed"

# 金額超過 1000 的訂單
high_value_orders = QB["amount"] > 1000

# 組合：本月完成的高額訂單
query = QB.all(
    this_month_orders,
    completed_orders,
    high_value_orders
)

# 按金額降序
query = query.sort(QB["amount"].desc())

results = order_manager.search_resources(query)
```

---

## 常見問題

### Q: 如何查詢嵌套欄位？

A: 使用點號表示法：

```python
QB["user.profile.bio"].contains("developer")
QB["address.city"] == "Taipei"
```

### Q: 如何處理特殊字元欄位名？

A: 使用方括號和字串：

```python
QB["field-with-dashes"] > 10
QB["field.with.dots"] == "value"
QB["field with spaces"].contains("text")
```

### Q: 如何組合多個可選條件？

A: 使用列表和 `QB.all()`：

```python
conditions = []
if age_filter:
    conditions.append(QB["age"] >= age_filter)
if status_filter:
    conditions.append(QB["status"] == status_filter)

query = QB.all(*conditions) if conditions else QB.all()

# 簡化寫法（推薦）
query = QB.all(*conditions)  # 空 list 時自動匹配所有資源
```

### Q: 查詢效能如何優化？

A: 

1. 使用索引欄位查詢
2. 將選擇性高的條件放前面
3. 使用 `in_()` 代替多個 OR
4. 避免過度複雜的正則表達式
5. 合理使用 limit 限制返回數量

### Q: 如何查詢所有資源（無條件）？

A: 使用 `QB.all()` 不帶參數：

```python
query = QB.all()  # 無篩選條件
query = query.sort("-created_time").limit(100)
results = resource_manager.search_resources(query)
```

### Q: 運算符別名有哪些？

A: AutoCRUD Query Builder 提供了直觀的運算符別名：

```python
# << 代表 in_（包含於列表）
QB["status"] << ["active", "pending"]
# 等同於：QB["status"].in_(["active", "pending"])

# >> 代表 contains（包含子字串）
QB["name"] >> "王"
# 等同於：QB["name"].contains("王")

# ~ 代表 is_falsy（空值或假值）
~QB["comment"]
# 等同於：QB["comment"].is_falsy()
```
