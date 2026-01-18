# 🔍 Query Builder Complete Guide

---

## Introduction
!!! info "New in version 0.7.5"


AutoCRUD Query Builder provides a Pythonic API for building resource query conditions. It supports:

- 🔍 Rich query operators (`==`, `>`, `<<`, `>>`, etc.)
- 🔗 Intuitive chaining syntax
- 📅 Convenient datetime queries
- 🎯 Type-safe field references
- ⚡ High-performance query execution

## Quick Start

```python
from autocrud.query import QB

# Simple query
query = QB["age"] > 18

# Combined conditions
query = (QB["age"] > 18) & (QB["department"] == "Engineering")

# Execute the query with ResourceManager
results = resource_manager.search_resources(query)
```

## Core Concepts

### QB (Query Builder)

`QB` is the entry point of the query builder. Use bracket syntax to access fields:

```python
from autocrud.query import QB

# Access fields
age_field = QB["age"]
name_field = QB["name"]
email_field = QB["email"]

# Support special characters and dotted paths
dotted_field = QB["user.profile.bio"]
special_field = QB["field-with-dashes"]
```

### Field Objects

Each `QB["field_name"]` returns a `Field` object that provides various query methods:

```python
field = QB["age"]
condition = field.gt(18)  # Greater than 18

# Field can be used directly, equivalent to is_truthy()
QB["verified"]  # Check verified is truthy
QB["email"] & QB["verified"]  # Has email and is verified
~QB["deleted"]  # Check deleted is null or falsy
```

### ConditionBuilder

Query conditions return `ConditionBuilder` objects, which can be combined and chained:

```python
cond1 = QB["age"] > 18
cond2 = QB["age"] < 65
combined = cond1 & cond2  # AND combination
```

---

## Field Operations

### Basic Access

```python
# Use bracket syntax
QB["field_name"]
```

## API Reference Quick Lookup

### [Comparison Operators](#comparison-operators)

| Method                                        | Operator | Description           |
| --------------------------------------------- | -------- | --------------------- |
| `eq(value)`                                   | `==`     | Equals                |
| `ne(value)`                                   | `!=`     | Not equals            |
| `gt(value)`                                   | `>`      | Greater than          |
| `gte(value)`                                  | `>=`     | Greater than or equal |
| `lt(value)`                                   | `<`      | Less than             |
| `lte(value)`                                  | `<=`     | Less than or equal    |
| `in_(values)` <br> `one_of(values)`           | `<<`     | In list               |
| `not_in(values)`                              | -        | Not in list           |
| `between(min, max)` <br> `in_range(min, max)` | -        | Within range          |

### [String Queries](#string-queries)

| Method                                 | Operator | Description                           |
| -------------------------------------- | -------- | ------------------------------------- |
| `contains(s)`                          | `>>`     | Contains substring                    |
| `icontains(s)`                         | -        | Contains substring (case-insensitive) |
| `starts_with(s)`                       | -        | Starts with                           |
| `istarts_with(s)`                      | -        | Starts with (case-insensitive)        |
| `ends_with(s)`                         | -        | Ends with                             |
| `iends_with(s)`                        | -        | Ends with (case-insensitive)          |
| `not_contains(s)`                      | -        | Does not contain                      |
| `not_starts_with(s)`                   | -        | Does not start with                   |
| `not_ends_with(s)`                     | -        | Does not end with                     |
| `regex(pattern)` <br> `match(pattern)` | -        | Regex match                           |
| `like(pattern)`                        | -        | SQL LIKE pattern                      |
| `is_empty()`                           | -        | Empty string or NULL                  |
| `is_blank()`                           | -        | Blank (including whitespace)          |

### [Boolean Queries](#boolean-queries)

| Method        | Operator   | Description                               |
| ------------- | ---------- | ----------------------------------------- |
| `is_true()`   | -          | Equals True                               |
| `is_false()`  | -          | Equals False                              |
| `is_truthy()` | Direct use | Meaningful value (not None/False/0/""/[]) |
| `is_falsy()`  | `~`        | Null or falsy                             |

### [NULL Handling](#null-handling)

| Method                                                   | Operator | Description                     |
| -------------------------------------------------------- | -------- | ------------------------------- |
| `is_null(True)`                                          | -        | Is NULL                         |
| `is_null(False)` <br> `is_not_null()` <br> `has_value()` | -        | Is not NULL                     |
| `exists(True)`                                           | -        | Field exists                    |
| `exists(False)`                                          | -        | Field does not exist            |
| `isna(True)`                                             | -        | Not available (missing or NULL) |
| `isna(False)`                                            | -        | Available                       |

### [Datetime Queries](#datetime-queries)

| Method                            | Description |
| --------------------------------- | ----------- |
| `today(tz=None)`                  | Today       |
| `yesterday(tz=None)`              | Yesterday   |
| `this_week(start_day=0, tz=None)` | This week   |
| `this_month(tz=None)`             | This month  |
| `this_year(tz=None)`              | This year   |
| `last_n_days(n, tz=None)`         | Last N days |

### [Field Transforms](#field-transforms)

| Method     | Description                  |
| ---------- | ---------------------------- |
| `length()` | Get length (string or array) |

### [Sorting](#sorting)

| Method                                 | Description |
| -------------------------------------- | ----------- |
| `sort(*sorts)` <br> `order_by(*sorts)` | Sort        |
| `asc()`                                | Ascending   |
| `desc()`                               | Descending  |

### [Pagination](#pagination)

| Method             | Description           |
| ------------------ | --------------------- |
| `limit(n)`         | Limit count           |
| `offset(n)`        | Offset                |
| `page(n, size=10)` | Page-based pagination |
| `first()`          | First record          |

### [Logical Operations](#logical-operations)

| Method/Operator   | Description          |    |
| ----------------- | -------------------- | -- |
| `&`               | AND                  |    |
| `                 | `                    | OR |
| `~`               | NOT                  |    |
| `QB.all(*conds)`  | All conditions (AND) |    |
| `QB.any(*conds)`  | Any condition (OR)   |    |
| `filter(*conds)`  | Filter (AND)         |    |
| `exclude(*conds)` | Exclude (NOT OR)     |    |

---

<a id="comparison-operators"></a>

## Comparison Operators

### Equals / Not Equals

```python
# Equals
QB["status"] == "active"
QB["status"].eq("active")

# Example: query resources with status = active
active_resources = manager.search_resources(QB["status"] == "active")

# Not equals
QB["status"] != "deleted"
QB["status"].ne("deleted")

# Example: query users that are not deleted
not_deleted = manager.search_resources(QB["status"] != "deleted")
```

### Greater Than / Less Than

```python
# Greater than
QB["age"] > 18
QB["age"].gt(18)

# Example: query adult users
adults = manager.search_resources(QB["age"] > 18)

# Greater than or equal
QB["age"] >= 18
QB["age"].gte(18)

# Less than
QB["price"] < 100
QB["price"].lt(100)

# Example: query low-priced items
cheap_items = manager.search_resources(QB["price"] < 100)

# Less than or equal
QB["price"] <= 100
QB["price"].lte(100)
```

### In / Not In

```python
# Check whether a value is in a list
QB["status"].in_(["active", "pending", "approved"])
QB["status"].one_of(["active", "pending"])  # alias
QB["status"] << ["active", "pending", "approved"]  # << operator alias

# Example: query orders with multiple statuses
orders = manager.search_resources(
    QB["status"] << ["pending", "processing", "shipped"]
)

# Check whether a value is NOT in a list
QB["status"].not_in(["deleted", "banned"])

# Example: exclude deleted or banned users
valid_users = manager.search_resources(
    QB["status"].not_in(["deleted", "banned"])
)
```

---

<a id="logical-operations"></a>
## Logical Operations

### AND

```python
# Using the & operator
query = (QB["age"] > 18) & (QB["age"] < 65)

# Example: query users of working age
working_age = manager.search_resources(
    (QB["age"] >= 18) & (QB["age"] <= 65)
)

# Using QB.all()
query = QB.all(
    QB["age"] > 18,
    QB["age"] < 65,
    QB["status"] == "active"
)

# Example: active adult engineers
active_engineers = manager.search_resources(
    QB.all(
        QB["age"] >= 18,
        QB["status"] == "active",
        QB["department"] == "Engineering"
    )
)

# QB.all() with no arguments — query all resources
all_resources = manager.search_resources(QB.all())

# Using filter()
query = QB.filter(
    QB["age"] > 18,
    QB["status"] == "active"
)
```

### OR

```python
# Using the | operator
query = (QB["department"] == "Engineering") | (QB["department"] == "Sales")

# Example: query employees in Engineering or Sales
tech_or_sales = manager.search_resources(
    (QB["department"] == "Engineering") | (QB["department"] == "Sales")
)

# Using QB.any()
query = QB.any(
    QB["department"] == "Engineering",
    QB["department"] == "Sales",
    QB["department"] == "Marketing"
)
# Note: QB.any() requires at least one condition; empty arguments will raise ValueError

# Example: multi-department filter
multi_dept = manager.search_resources(
    QB.any(
        QB["department"] == "Engineering",
        QB["department"] == "Sales",
        QB["department"] == "Marketing"
    )
)
```

### NOT

```python
# Using the ~ operator
query = ~(QB["status"] == "deleted")

# Using exclude()
query = QB.exclude(
    QB["status"] == "deleted",
    QB["is_banned"] == True
)
```

### Filter and Exclude

`QB.filter()` and `QB.exclude()` provide more semantic query methods.

```python
# Filter — include matching conditions (AND logic)
query = QB.filter(
    QB["age"] > 18,
    QB["status"] == "active"
)
# Equivalent to: (age > 18) AND (status = 'active')

# Exclude — exclude matching conditions (NOT OR logic)
query = QB.exclude(
    QB["is_deleted"] == True,
    QB["is_banned"] == True
)
# Equivalent to: NOT (is_deleted = true OR is_banned = true)
```

### Complex Combinations

```python
# Use parentheses to control precedence
query = (
    (QB["age"] > 18) & (QB["age"] < 65)
) | (
    QB["is_premium"] == True
)

# Equivalent SQL:
# WHERE (age > 18 AND age < 65) OR is_premium = true
```

---

<a id="string-queries"></a>
## String Queries

### Contains / Starts With / Ends With

```python
# Contains substring
QB["name"].contains("John")
QB["name"] >> "John"  # >> operator alias
QB["description"].contains("urgent")

# Example: search users whose name contains "王"
wang_users = manager.search_resources(QB["name"] >> "王")

# Example: search tasks whose description contains "urgent"
urgent_tasks = manager.search_resources(
    QB["description"].contains("urgent")
)

# Starts with
QB["email"].starts_with("admin")
QB["code"].starts_with("PRE-")

# Example: query admin accounts
admins = manager.search_resources(
    QB["email"].starts_with("admin")
)

# Ends with
QB["email"].ends_with("@gmail.com")
QB["filename"].ends_with(".pdf")

# Example: query Gmail users
gmail_users = manager.search_resources(
    QB["email"].ends_with("@gmail.com")
)
```
### Case-Insensitive

```python
# Case-insensitive contains
QB["name"].icontains("john")  # Matches "John", "JOHN", "john"

# Case-insensitive starts with
QB["email"].istarts_with("admin")  # Matches "Admin@", "ADMIN@"

# Case-insensitive ends with
QB["filename"].iends_with(".pdf")  # Matches ".PDF", ".Pdf"
```

### Negation Queries

```python
# Does not contain
QB["description"].not_contains("spam")

# Does not start with
QB["email"].not_starts_with("test")

# Does not end with
QB["filename"].not_ends_with(".tmp")
```

### Regular Expressions

```python
# Use regular expressions
QB["email"].regex(r".*@gmail\.com$")
QB["phone"].regex(r"^\+886-\d{9}$")
QB["code"].match(r"^[A-Z]{3}-\d{4}$")  # match() is an alias of regex()
```

### SQL LIKE Patterns

```python
# % means any sequence of characters, _ means a single character
QB["name"].like("A%")           # Starts with A
QB["email"].like("%@gmail.com") # Ends with @gmail.com
QB["code"].like("A_C")          # Matches ABC, A1C, etc.
QB["desc"].like("%urgent%")     # Contains urgent
```

### Null Checks

```python
# Empty string or null
QB["description"].is_empty()

# Blank (empty string, null, or whitespace only)
QB["comment"].is_blank()  # Matches "", null, "  ", "\t\n"
```

---

## Numeric and Range Queries

### Range Queries

```python
# Between (inclusive)
QB["age"].between(18, 65)
QB["price"].in_range(100, 1000)  # Alias

# Example: query users in a specific age range
working_age = manager.search_resources(QB["age"].between(18, 65))

# Example: query mid-range priced products
mid_range = manager.search_resources(
    QB["price"].between(1000, 5000)
)

# Manual combination
(QB["age"] >= 18) & (QB["age"] <= 65)
```

### Mathematical Operations

```python
# Basic comparisons
QB["quantity"] > 0
QB["balance"] >= 1000
QB["discount"] <= 0.5

# Combined conditions
(QB["price"] > 100) & (QB["price"] < 1000)
```

---

<a id="datetime-queries"></a>
## Date and Time Queries

### Today

```python
# Today (default local timezone)
QB.created_time.today()

# Specify timezone (UTC+8)
QB.created_time.today(tz=8)
QB.created_time.today(tz="+8")

# Use ZoneInfo
from zoneinfo import ZoneInfo
QB.created_time.today(tz=ZoneInfo("Asia/Taipei"))
```

### Yesterday

```python
QB.created_time.yesterday()
QB.updated_time.yesterday(tz=8)
```

### This Week

```python
# This week (Monday by default)
QB.created_time.this_week()

# Specify week start day (0=Monday, 6=Sunday)
QB.created_time.this_week(start_day=6)  # Start on Sunday

# Specify timezone
QB.created_time.this_week(tz=8)
```

### This Month

```python
QB.created_time.this_month()
QB.created_time.this_month(tz=8)
```

### This Year

```python
QB.created_time.this_year()
QB.created_time.this_year(tz=8)
```

### Last N Days

```python
# Last 7 days
QB.created_time.last_n_days(7)

# Last 30 days
QB.created_time.last_n_days(30, tz=8)
```

### Date Range

```python
import datetime as dt

start = dt.datetime(2024, 1, 1)
end = dt.datetime(2024, 12, 31)

QB.created_time.between(start, end)
```

### Combined Date Queries

```python
# Created today and updated this week
query = QB.created_time.today() & QB.updated_time.this_week()

# Created in the last 7 days or updated today
query = QB.created_time.last_n_days(7) | QB.updated_time.today()
```

---

<a id="boolean-queries"></a>
## Boolean Queries

### True / False

```python
# Equals True
QB["is_active"].is_true()
QB["is_active"] == True

# Equals False
QB["is_deleted"].is_false()
QB["is_deleted"] == False
```
### Truthy / Falsy

```python
# Truthy (meaningful values)
# Excludes: None, False, 0, "", []
QB["status"].is_truthy()
QB["status"]  # Using Field directly is equivalent to is_truthy()

# Example: query resources with a status value
with_status = manager.search_resources(QB["status"])  # concise syntax!

# Falsy (empty or false values)
# Matches: None, False, 0, "", []
QB["comment"].is_falsy()
~QB["comment"]  # ~ operator alias

# Example: query tasks without comments
no_comment = manager.search_resources(~QB["comment"])

# Example: query articles with empty tags or no tags
empty_tags = manager.search_resources(~QB["tags"])

# Combined usage
query = QB["verified"] & QB["email"]  # verified and has email
query = (QB["status"] == "active") & ~QB["comment"]  # active and no comment
```

### Examples

```python
# Active users with tags (using operators)
query = (QB["is_active"] == True) & QB["tags"]  # tags.is_truthy()

# Active tasks without comments
query = (QB["status"] == "active") & ~QB["comment"]

# Verified users with email and not deleted
query = QB["verified"] & QB["email"] & ~QB["deleted_at"]

# Deleted or banned users
query = QB["is_deleted"].is_true() | QB["is_banned"].is_true()
```

---

<a id="field-transforms"></a>
## Field Transforms

### Length Queries

```python
# Using the .length() method
QB["name"].length() > 5
QB["tags"].length() == 0
QB["email"].length().between(10, 50)

# Example: query users with a moderate name length
moderate_name = manager.search_resources(
    QB["name"].length().between(3, 20)
)
```

### String Length

```python
# Name length greater than 5 characters
QB["name"].length() > 5

# Description length between 100 and 500
QB["description"].length().between(100, 500)

# Example: query products with detailed descriptions
detailed = manager.search_resources(
    QB["description"].length() > 100
)

# Email address at least 10 characters
QB["email"].length() >= 10
```

### Array/List Length

```python
# More than 3 tags
QB["tags"].length() > 3

# No tags (empty list)
QB["tags"].length() == 0

# Example: query tagged articles
tagged_articles = manager.search_resources(
    QB["tags"].length() > 0
)

# At least 1 item
QB["items"].length() >= 1
```

### Combined Length Queries

```python
# Moderate name length and has tags
query = (QB["name"].length().between(3, 20)) & (QB["tags"].length() > 0)

# Example: query products with reasonable names and categories
valid_products = manager.search_resources(
    (QB["name"].length().between(5, 50)) & (QB["categories"].length() > 0)
)

# Empty or very short description
query = (QB["description"].length() == 0) | (QB["description"].length() < 10)
```

---

<a id="null-handling"></a>
## NULL and Empty Value Handling

### NULL Checks

```python
# Is NULL
QB["deleted_at"].is_null()
QB["deleted_at"].is_null(True)

# Example: query non-deleted resources
active = manager.search_resources(QB["deleted_at"].is_null())

# Is NOT NULL
QB["deleted_at"].is_null(False)
QB["email"].is_not_null()  # alias
QB["email"].has_value()     # alias

# Example: query users with email
with_email = manager.search_resources(QB["email"].is_not_null())
```

### Field Existence

```python
# Field exists (even if value is NULL)
QB["optional_field"].exists()
QB["optional_field"].exists(True)

# Field does not exist
QB["optional_field"].exists(False)
```

### Is NA (Not Available)

```python
# Not available (does not exist or is NULL)
QB["archived_at"].isna()
QB["archived_at"].isna(True)

# Example: query tasks without comments
no_comment = manager.search_resources(QB["comment"].isna())

# Available (exists and is not NULL)
QB["archived_at"].isna(False)

# Example: query archived resources
archived = manager.search_resources(QB["archived_at"].isna(False))
```

### Differences Explained

```python
# is_null: field exists and value is NULL
QB["field"].is_null(True)   # field exists AND field = NULL

# exists: whether the field exists (regardless of value)
QB["field"].exists(True)    # field exists (value can be anything including NULL)

# isna: field does not exist or is NULL
QB["field"].isna(True)      # field does NOT exist OR field = NULL
```

---

<a id="sorting"></a>
## Sorting

### Basic Sorting

```python
# Ascending
query = QB["age"] > 18
query = query.sort(QB["age"].asc())

# Descending
query = query.sort(QB["age"].desc())
```
### String-based Sorting Syntax

```python
# Use string syntax (ascending by default)
query.sort("age")           # Ascending
query.sort("+age")          # Explicit ascending
query.sort("-age")          # Descending

# Alias: order_by
query.order_by("-created_time")
```

### Multi-field Sorting

```python
# Sort by department ascending, then by age descending
query.sort(
    QB["department"].asc(),
    QB["age"].desc()
)

# Using string syntax
query.sort("department", "-age")
```

### Sorting by Meta Fields

```python
# Sort by created time descending
query.sort(QB.created_time.desc())

# Sort by updated time ascending
query.sort(QB.updated_time.asc())

# Combined sorting
query.sort(
    QB.created_time.desc(),  # Meta field
    QB["name"].asc()         # Data field
)
```

---

<a id="pagination"></a>
## Pagination

### Limit and Offset

```python
# Limit the number of results
query = QB["status"] == "active"
query = query.limit(10)

# Offset
query = query.offset(20)

# Combined usage (page 3, 10 items per page)
query.limit(10).offset(20)
```

### Page-based Pagination

```python
# Page 1 (10 items per page by default)
query.page(1)

# Page 2, 20 items per page
query.page(2, size=20)

# Custom page size
query.page(3, size=50)
```

### First Method

```python
# Fetch only the first record
query = QB["email"] == "admin@example.com"
query = query.first()  # Equivalent to limit(1)
```

### Pagination Formula

```python
# page(n, size=s) is equivalent to:
# limit(s).offset((n-1) * s)

query.page(1, size=10)  # limit(10).offset(0)
query.page(2, size=10)  # limit(10).offset(10)
query.page(3, size=10)  # limit(10).offset(20)
```

---

## Combined Queries

### Complex AND/OR Combinations

```python
# (A AND B) OR (C AND D)
query = (
    (QB["age"] > 18) & (QB["department"] == "Engineering")
) | (
    (QB["is_premium"] == True) & (QB["status"] == "active")
)
```

### Using Helper Methods

```python
# QB.all() - all conditions must be satisfied
query = QB.all(
    QB["age"] > 18,
    QB["age"] < 65,
    QB["status"] == "active",
    QB["is_verified"] == True
)

# QB.all() with no arguments - query all resources (no conditions)
query = QB.all()  # Equivalent to no conditions

# QB.any() - at least one condition must be satisfied
query = QB.any(
    QB["role"] == "admin",
    QB["role"] == "moderator",
    QB["role"] == "manager"
)
# Note: QB.any() requires at least one condition, otherwise it raises ValueError
```



### Practical Examples

```python
# Query active adult engineers or administrators
query = QB.filter(
    QB["status"] == "active",
    QB["age"] >= 18
) & QB.any(
    QB["department"] == "Engineering",
    QB["role"] == "admin"
)

# Exclude deleted and banned users
query = QB["status"] == "active"
query = query.exclude(
    QB["is_deleted"] == True,
    QB["is_banned"] == True
)
```

---

## Meta Field Queries

### Available Meta Fields

```python
QB.resource_id          # Resource ID
QB.created_time         # Created time
QB.updated_time         # Updated time
QB.created_by           # Created by
QB.updated_by           # Updated by
QB.is_deleted           # Whether deleted
QB.current_revision_id  # Current revision ID
QB.total_revision_count # Total revision count
```

### Meta Field Query Examples

```python
# Resources created by a specific user
QB.created_by == "user123"

# Resources updated today
QB.updated_time.today()

# Non-deleted resources
QB.is_deleted == False

# Resources with multiple revisions
QB.total_revision_count > 1

# Specific resource IDs
QB.resource_id.in_(["id1", "id2", "id3"])
```

### Combining Meta and Data Queries

```python
# Active users created today
query = QB.created_time.today() & (QB["status"] == "active")

# Resources updated this week and not deleted
query = QB.updated_time.this_week() & (QB.is_deleted == False)

# Engineering department resources created by a specific user
query = (QB.created_by == "user123") & (QB["department"] == "Engineering")
```
## Advanced Techniques

### Dynamic Query Construction

```python
# Dynamically build queries based on conditions
conditions = []

if age_min is not None:
    conditions.append(QB["age"] >= age_min)

if age_max is not None:
    conditions.append(QB["age"] <= age_max)

if department:
    conditions.append(QB["department"] == department)

# Combine all conditions
if conditions:
    query = QB.all(*conditions)
else:
    query = QB.all()  # Unconditional query (matches all resources)
```

### Query Reuse

```python
# Define a base query
active_users = QB["status"] == "active"

# Add conditions on top of the base query
adult_active_users = active_users & (QB["age"] >= 18)
premium_active_users = active_users & (QB["is_premium"] == True)

# Reuse multiple times
results1 = resource_manager.search_resources(adult_active_users)
results2 = resource_manager.search_resources(premium_active_users)
```

### Query Transformation

```python
# Build a query
query = QB["age"] > 18
query = query.sort("-created_time")
query = query.limit(10)

# Convert to ResourceMetaSearchQuery
search_query = query.build()

# Pass directly to ResourceManager
results = resource_manager.search_resources(query)
```

### Field Name Variables

```python
# Store field names in variables
field_name = "email"
domain = "@gmail.com"

query = QB[field_name].ends_with(domain)

# Dynamic field query
def search_by_field(field_name, value):
    return QB[field_name] == value

query = search_by_field("status", "active")
```

### Common Query Patterns

```python
# 1. Pagination pattern
def get_page(page_num, page_size=20, filters=None):
    query = filters if filters else QB.all()
    return query.page(page_num, size=page_size)

# 2. Search pattern (multi-field OR)
def search_users(keyword):
    return QB.any(
        QB["name"].icontains(keyword),
        QB["email"].icontains(keyword),
        QB["username"].icontains(keyword)
    )

# 3. Time range filter
def created_between(start, end):
    return QB.created_time.between(start, end)

# 4. Status filter
def active_resources():
    return QB.all(
        QB["status"] == "active",
        QB.is_deleted == False
    )
```

### Performance Optimization Tips

```python
# ✅ Good: use indexed fields
query = QB["indexed_field"] == "value"

# ✅ Good: use in_ instead of multiple ORs
query = QB["status"].in_(["active", "pending", "approved"])

# ❌ Avoid: overly complex regular expressions
query = QB["field"].regex(r"^(?=.*[A-Z])(?=.*[0-9])(?=.*[@#$%]).{8,}$")

# ✅ Good: place frequently used conditions first
query = (QB["status"] == "active") & (QB["complex_field"].regex("..."))
```

---

## Complete Examples

### E-commerce Product Query

```python
from autocrud.query import QB

# Active products priced between 100 and 1000, with at least 3 tags
query = QB.all(
    QB["price"].between(100, 1000),
    QB["status"] == "active",
    QB["tags"].length() >= 3
)

# Sort by price ascending and take the first 20
query = query.sort("price").limit(20)

results = product_manager.search_resources(query)
```

### User Management Query

```python
# Active adult users with activity in the last 30 days
query = QB.all(
    QB["status"] == "active",
    QB["age"] >= 18,
    QB.updated_time.last_n_days(30)
)

# Exclude deleted and banned users
query = query.exclude(
    QB["is_deleted"] == True,
    QB["is_banned"] == True
)

# Sort by last activity time descending
query = query.sort(QB.updated_time.desc())

results = user_manager.search_resources(query)
```

### Content Search Query

```python
# Search for articles whose title or content contains the keyword
keyword = "Python"

query = QB.any(
    QB["title"].icontains(keyword),
    QB["content"].icontains(keyword),
    QB["tags"].contains(keyword.lower())
)

# Search only published articles
query = query & (QB["status"] == "published")

# Sort by relevance (updated time) descending
query = query.sort(QB.updated_time.desc()).limit(50)

results = article_manager.search_resources(query)
```

### Reporting and Analytics Query

```python
# Orders created this month
this_month_orders = QB.created_time.this_month()

# Completed orders
completed_orders = QB["status"] == "completed"

# Orders with amount greater than 1000
high_value_orders = QB["amount"] > 1000

# Combine: high-value completed orders from this month
query = QB.all(
    this_month_orders,
    completed_orders,
    high_value_orders
)

# Sort by amount descending
query = query.sort(QB["amount"].desc())

results = order_manager.search_resources(query)
```

---

## FAQ

### Q: How do I query nested fields?

A: Use dot notation:

```python
QB["user.profile.bio"].contains("developer")
QB["address.city"] == "Taipei"
```

### Q: How do I handle field names with special characters?

A: Use bracket notation with strings:

```python
QB["field-with-dashes"] > 10
QB["field.with.dots"] == "value"
QB["field with spaces"].contains("text")
```

### Q: How do I combine multiple optional conditions?

A: Use a list and `QB.all()`:

```python
conditions = []
if age_filter:
    conditions.append(QB["age"] >= age_filter)
if status_filter:
    conditions.append(QB["status"] == status_filter)

query = QB.all(*conditions) if conditions else QB.all()

# Simplified form (recommended)
query = QB.all(*conditions)  # Automatically matches all resources when the list is empty
```

### Q: How can I optimize query performance?

A:

1. Query using indexed fields
2. Put highly selective conditions first
3. Use `in_()` instead of multiple ORs
4. Avoid overly complex regular expressions
5. Use `limit` appropriately to cap the result size

### Q: How do I query all resources (no conditions)?

A: Use `QB.all()` without parameters:

```python
query = QB.all()  # No filter conditions
query = query.sort("-created_time").limit(100)
results = resource_manager.search_resources(query)
```

### Q: What operator aliases are available?

A: AutoCRUD Query Builder provides intuitive operator aliases:

```python
# << represents in_ (contained in a list)
QB["status"] << ["active", "pending"]
# Equivalent to: QB["status"].in_(["active", "pending"])

# >> represents contains (substring match)
QB["name"] >> "王"
# Equivalent to: QB["name"].contains("王")

# ~ represents is_falsy (null or falsy)
~QB["comment"]
# Equivalent to: QB["comment"].is_falsy()
```
