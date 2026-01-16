import datetime as dt
from zoneinfo import ZoneInfo
from msgspec import UNSET
import pytest
from autocrud.query import QB, ConditionBuilder
from autocrud.types import (
    DataSearchCondition,
    DataSearchGroup,
    DataSearchLogicOperator,
    DataSearchOperator,
    ResourceDataSearchSort,
    ResourceMeta,
    ResourceMetaSortKey,
    ResourceMetaSortDirection,
    ResourceMetaSearchQuery,
    IndexableField,
)
from autocrud.resource_manager.core import ResourceManager
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.resource_manager.core import SimpleStorage


class TestQueryBuilder:
    def test_simple_condition(self):
        q = QB["name"].eq("Alice")
        assert isinstance(q, ConditionBuilder)
        query = q.build()
        assert isinstance(query, ResourceMetaSearchQuery)
        assert query.conditions is not UNSET
        assert len(query.conditions) == 1
        condition = query.conditions[0]
        assert isinstance(condition, DataSearchCondition)
        assert condition.field_path == "name"
        assert condition.operator == DataSearchOperator.equals
        assert condition.value == "Alice"

    def test_and_condition(self):
        q = QB["name"].eq("Alice") & QB["age"].gt(30)
        query = q.build()
        assert len(query.conditions) == 1
        group = query.conditions[0]
        assert isinstance(group, DataSearchGroup)
        assert group.operator == DataSearchLogicOperator.and_op
        assert len(group.conditions) == 2

        c1 = group.conditions[0]
        assert isinstance(c1, DataSearchCondition)
        assert c1.field_path == "name"
        assert c1.value == "Alice"

        c2 = group.conditions[1]
        assert isinstance(c2, DataSearchCondition)
        assert c2.field_path == "age"
        assert c2.operator == DataSearchOperator.greater_than
        assert c2.value == 30

    def test_or_condition(self):
        q = QB["name"].eq("Alice") | QB["name"].eq("Bob")
        query = q.build()
        group = query.conditions[0]
        assert isinstance(group, DataSearchGroup)
        assert group.operator == DataSearchLogicOperator.or_op
        assert len(group.conditions) == 2

    def test_complex_condition(self):
        # (name == "Alice" AND age > 30) OR (department == "HR" AND active == True)
        q = (QB["name"].eq("Alice") & QB["age"].gt(30)) | (
            QB["department"].eq("HR") & QB["active"].eq(True)
        )
        query = q.build()
        group = query.conditions[0]
        assert isinstance(group, DataSearchGroup)
        assert group.operator == DataSearchLogicOperator.or_op
        assert len(group.conditions) == 2

        g1 = group.conditions[0]
        assert isinstance(g1, DataSearchGroup)
        assert g1.operator == DataSearchLogicOperator.and_op

        g2 = group.conditions[1]
        assert isinstance(g2, DataSearchGroup)
        assert g2.operator == DataSearchLogicOperator.and_op

    def test_sort_limit_offset(self):
        q = (
            QB["age"]
            .gt(20)
            .sort(QB.created_time().desc())
            .sort(QB["age"].asc())
            .limit(5)
            .offset(10)
        )
        query = q.build()

        assert query.limit == 5
        assert query.offset == 10
        assert query.sorts is not UNSET
        assert len(query.sorts) == 2

        s1 = query.sorts[0]
        assert s1.key == ResourceMetaSortKey.created_time
        assert s1.direction == ResourceMetaSortDirection.descending

        s2 = query.sorts[1]
        assert isinstance(s2, ResourceDataSearchSort)
        assert s2.field_path == "age"
        assert s2.direction == ResourceMetaSortDirection.ascending

    def test_page_first_page(self):
        """Test page() for first page."""
        q = QB["status"].eq("active").page(1, 10)
        query = q.build()
        assert query.limit == 10
        assert query.offset == 0

    def test_page_second_page(self):
        """Test page() for second page."""
        q = QB["status"].eq("active").page(2, 20)
        query = q.build()
        assert query.limit == 20
        assert query.offset == 20

    def test_page_default_size(self):
        """Test page() with default size."""
        q = QB["status"].eq("active").page(3)
        query = q.build()
        assert query.limit == 20
        assert query.offset == 40

    def test_page_third_page_custom_size(self):
        """Test page() for third page with custom size."""
        q = QB["status"].eq("active").page(3, 15)
        query = q.build()
        assert query.limit == 15
        assert query.offset == 30

    def test_page_invalid_page_number(self):
        """Test page() with invalid page number."""
        with pytest.raises(ValueError, match="Page number must be >= 1"):
            QB["status"].eq("active").page(0, 10)

    def test_page_invalid_size(self):
        """Test page() with invalid size."""
        with pytest.raises(ValueError, match="Page size must be >= 1"):
            QB["status"].eq("active").page(1, 0)

    def test_first_method(self):
        """Test first() sets limit to 1."""
        q = QB["status"].eq("active").first()
        query = q.build()
        assert query.limit == 1

    def test_first_with_sorting(self):
        """Test first() combined with sorting."""
        q = QB["status"].eq("active").sort(QB.created_time().desc()).first()
        query = q.build()
        assert query.limit == 1
        assert query.sorts is not UNSET
        assert len(query.sorts) == 1

    def test_page_with_sorting(self):
        """Test page() combined with sorting."""
        q = QB["status"].eq("active").sort(QB["age"].asc()).page(2, 15)
        query = q.build()
        assert query.limit == 15
        assert query.offset == 15
        assert query.sorts is not UNSET

    def test_nested_field(self):
        q = QB["user.profile.email"].eq("test@example.com")
        query = q.build()
        condition = query.conditions[0]
        assert condition.field_path == "user.profile.email"
        assert condition.value == "test@example.com"

    def test_all_operators(self):
        """Test all supported operators in Field class."""
        field = QB["test_field"]

        # eq
        c = field.eq(1).build().conditions[0]
        assert c.operator == DataSearchOperator.equals
        assert c.value == 1

        # ne
        c = field.ne(1).build().conditions[0]
        assert c.operator == DataSearchOperator.not_equals

        # gt
        c = field.gt(1).build().conditions[0]
        assert c.operator == DataSearchOperator.greater_than

        # gte
        c = field.gte(1).build().conditions[0]
        assert c.operator == DataSearchOperator.greater_than_or_equal

        # lt
        c = field.lt(1).build().conditions[0]
        assert c.operator == DataSearchOperator.less_than

        # lte
        c = field.lte(1).build().conditions[0]
        assert c.operator == DataSearchOperator.less_than_or_equal

        # contains
        c = field.contains("x").build().conditions[0]
        assert c.operator == DataSearchOperator.contains

        # starts_with
        c = field.starts_with("x").build().conditions[0]
        assert c.operator == DataSearchOperator.starts_with

        # ends_with
        c = field.ends_with("x").build().conditions[0]
        assert c.operator == DataSearchOperator.ends_with

        # in_
        c = field.in_([1, 2]).build().conditions[0]
        assert c.operator == DataSearchOperator.in_list
        assert c.value == [1, 2]

        # not_in
        c = field.not_in([1, 2]).build().conditions[0]
        assert c.operator == DataSearchOperator.not_in_list

        # is_null
        c = field.is_null().build().conditions[0]
        assert c.operator == DataSearchOperator.is_null
        assert c.value is True

        # exists
        c = field.exists().build().conditions[0]
        assert c.operator == DataSearchOperator.exists

        # isna
        c = field.isna().build().conditions[0]
        assert c.operator == DataSearchOperator.isna

        # regex
        c = field.regex(".*").build().conditions[0]
        assert c.operator == DataSearchOperator.regex

    def test_invert_operator(self):
        """Test the ~ (not) operator."""
        q = ~QB["age"].gt(18)
        query = q.build()
        group = query.conditions[0]
        assert isinstance(group, DataSearchGroup)
        assert group.operator == DataSearchLogicOperator.not_op
        assert len(group.conditions) == 1

        inner = group.conditions[0]
        assert inner.field_path == "age"
        assert inner.operator == DataSearchOperator.greater_than

    def test_nested_logic_transformation(self):
        """Test complex nested logic: (A & B) | ~(C & D)"""
        q = (QB["a"].eq(1) & QB["b"].eq(2)) | ~(QB["c"].eq(3) & QB["d"].eq(4))
        query = q.build()

        root_group = query.conditions[0]
        assert root_group.operator == DataSearchLogicOperator.or_op
        assert len(root_group.conditions) == 2

        # Left side: A & B
        left = root_group.conditions[0]
        assert left.operator == DataSearchLogicOperator.and_op
        assert len(left.conditions) == 2

        # Right side: ~(C & D)
        right = root_group.conditions[1]
        assert right.operator == DataSearchLogicOperator.not_op
        assert len(right.conditions) == 1

        # Inside Not: C & D
        inner_right = right.conditions[0]
        assert inner_right.operator == DataSearchLogicOperator.and_op
        assert len(inner_right.conditions) == 2

    def test_invert_dual_usage(self):
        """Test ~ operator has different meanings for Field vs ConditionBuilder."""
        # Case 1: ~Field -> is_falsy() which is NOT(is_truthy)
        q1 = ~QB["comment"]
        cond1 = q1.build().conditions[0]
        assert isinstance(cond1, DataSearchGroup)
        assert cond1.operator == DataSearchLogicOperator.not_op
        assert len(cond1.conditions) == 1

        # Inside NOT is the truthy condition (AND group)
        inner_truthy = cond1.conditions[0]
        assert isinstance(inner_truthy, DataSearchGroup)
        assert inner_truthy.operator == DataSearchLogicOperator.and_op
        assert (
            len(inner_truthy.conditions) == 5
        )  # not null, not false, not 0, not "", not []

        # Case 2: ~(condition) -> NOT condition (logical negation)
        q2 = ~(QB["age"] > 18)
        query2 = q2.build()
        group = query2.conditions[0]
        assert isinstance(group, DataSearchGroup)
        assert group.operator == DataSearchLogicOperator.not_op
        assert len(group.conditions) == 1

        inner = group.conditions[0]
        assert inner.field_path == "age"
        assert inner.operator == DataSearchOperator.greater_than
        assert inner.value == 18

        # Case 3: Complex - NOT (field1 > 10 AND field2 < 20)
        q3 = ~((QB["score"] > 80) & (QB["age"] < 30))
        query3 = q3.build()
        root = query3.conditions[0]
        assert root.operator == DataSearchLogicOperator.not_op
        assert len(root.conditions) == 1

        inner_group = root.conditions[0]
        assert inner_group.operator == DataSearchLogicOperator.and_op

        # Case 4: ~~Field -> NOT(NOT(is_truthy())) 雙重否定
        q4 = ~~QB["optional_field"]
        query4 = q4.build()
        double_not = query4.conditions[0]
        assert isinstance(double_not, DataSearchGroup)
        assert double_not.operator == DataSearchLogicOperator.not_op
        assert len(double_not.conditions) == 1

        # Inside the first NOT is another NOT (is_falsy which is NOT(is_truthy))
        inner_not = double_not.conditions[0]
        assert isinstance(inner_not, DataSearchGroup)
        assert inner_not.operator == DataSearchLogicOperator.not_op
        assert len(inner_not.conditions) == 1

        # Inside the second NOT is is_truthy (AND group)
        inner_truthy = inner_not.conditions[0]
        assert isinstance(inner_truthy, DataSearchGroup)
        assert inner_truthy.operator == DataSearchLogicOperator.and_op
        assert (
            len(inner_truthy.conditions) == 5
        )  # not null, not false, not 0, not "", not []

    def test_between_range_query(self):
        """Test between() method for range queries."""
        # Basic range
        q = QB["age"].between(18, 65)
        query = q.build()
        cond = query.conditions[0]
        assert isinstance(cond, DataSearchGroup)
        assert cond.operator == DataSearchLogicOperator.and_op
        assert len(cond.conditions) == 2

        # First condition: age >= 18
        first = cond.conditions[0]
        assert first.field_path == "age"
        assert first.operator == DataSearchOperator.greater_than_or_equal
        assert first.value == 18

        # Second condition: age <= 65
        second = cond.conditions[1]
        assert second.field_path == "age"
        assert second.operator == DataSearchOperator.less_than_or_equal
        assert second.value == 65

    def test_between_with_other_operators(self):
        """Test between() combined with other conditions."""
        # Age between 18-65 AND status is active
        q = QB["age"].between(18, 65) & (QB["status"] == "active")
        query = q.build()
        root = query.conditions[0]
        assert root.operator == DataSearchLogicOperator.and_op
        assert len(root.conditions) == 2

        # First: age between
        age_cond = root.conditions[0]
        assert age_cond.operator == DataSearchLogicOperator.and_op

        # Second: status condition
        status_cond = root.conditions[1]
        assert status_cond.field_path == "status"
        assert status_cond.operator == DataSearchOperator.equals

    def test_between_with_datetime(self):
        """Test between() with datetime values."""
        import datetime as dt

        start = dt.datetime(2024, 1, 1)
        end = dt.datetime(2024, 12, 31)

        q = QB.created_time().between(start, end)
        query = q.build()
        cond = query.conditions[0]
        assert isinstance(cond, DataSearchGroup)
        assert len(cond.conditions) == 2
        assert cond.conditions[0].value == start
        assert cond.conditions[1].value == end

    def test_chained_comparison_conditional_builder(self):
        """Test chained comparison: min <= condition <= max."""
        # This tests the ConditionBuilder dunder methods
        # 100 <= QB["price"] <= 500 becomes (100 <= QB["price"]) and (QB["price"] <= 500)
        # First part: 100 <= QB["price"] returns ConditionBuilder with condition price >= 100
        # Second part: ConditionBuilder <= 500 should return ConditionBuilder with condition price <= 500

        q = 100 <= QB["price"] <= 500
        query = q.build()
        cond = query.conditions[0]

        # This should be price <= 500 (the last condition applied)
        assert cond.field_path == "price"
        assert cond.operator == DataSearchOperator.less_than_or_equal
        assert cond.value == 500

        # Note: The chained comparison only keeps the last condition
        # For proper range queries, use between() instead:
        q2 = QB["price"].between(100, 500)
        query2 = q2.build()
        cond2 = query2.conditions[0]
        assert isinstance(cond2, DataSearchGroup)
        assert cond2.operator == DataSearchLogicOperator.and_op

    def test_chained_equality_comparison(self):
        """Test chained equality: QB["foo"] == QB["bar"] == 2."""
        # QB["foo"] == QB["bar"] returns ConditionBuilder
        # ConditionBuilder == 2 should create condition bar == 2
        q = QB["foo"] == QB["bar"] == 2
        query = q.build()
        cond = query.conditions[0]

        # Should be bar == 2 (the last condition applied)
        assert cond.field_path == "bar"
        assert cond.operator == DataSearchOperator.equals
        assert cond.value == 2

    def test_chained_not_equals_comparison(self):
        """Test chained not-equals: QB["foo"] != QB["bar"] != 3."""
        q = QB["foo"] != QB["bar"] != 3
        query = q.build()
        cond = query.conditions[0]

        # Should be bar != 3
        assert cond.field_path == "bar"
        assert cond.operator == DataSearchOperator.not_equals
        assert cond.value == 3

    def test_conditionbuilder_eq_ne_with_values(self):
        """Test ConditionBuilder __eq__ and __ne__ with different value types."""
        # String values
        q1 = QB["status"] == QB["type"] == "active"
        assert q1.build().conditions[0].value == "active"

        # Integer values
        q2 = QB["count"] == QB["total"] == 100
        assert q2.build().conditions[0].value == 100

        # None values
        q3 = QB["value"] == QB["other"] == None  # noqa: E711
        assert q3.build().conditions[0].value is None

        # List values
        q4 = QB["tags"] != QB["labels"] != ["test"]
        assert q4.build().conditions[0].value == ["test"]

    def test_conditionbuilder_eq_with_logical_group_raises(self):
        """Test that __eq__ raises TypeError on logical groups."""
        # Create a logical group
        group = (QB["age"] > 18) & (QB["status"] == "active")

        # Should raise TypeError when trying to use == on a group
        with pytest.raises(TypeError, match="single conditions, not logical groups"):
            _ = group == 2

    def test_conditionbuilder_ne_with_logical_group_raises(self):
        """Test that __ne__ raises TypeError on logical groups."""
        group = (QB["age"] > 18) | (QB["score"] < 50)

        with pytest.raises(TypeError, match="single conditions, not logical groups"):
            _ = group != 5

    def test_qb_all_combinator(self):
        """Test QB.all() to combine multiple conditions with AND."""
        from autocrud.query import QB

        # Basic all() with multiple conditions
        q = QB.all(QB["age"] > 18, QB["status"] == "active", QB["score"] >= 80)
        query = q.build()
        root = query.conditions[0]

        assert isinstance(root, DataSearchGroup)
        assert root.operator == DataSearchLogicOperator.and_op
        assert len(root.conditions) == 3

        # First: age > 18
        assert root.conditions[0].field_path == "age"
        assert root.conditions[0].operator == DataSearchOperator.greater_than
        assert root.conditions[0].value == 18

        # Second: status == "active"
        assert root.conditions[1].field_path == "status"
        assert root.conditions[1].operator == DataSearchOperator.equals
        assert root.conditions[1].value == "active"

        # Third: score >= 80
        assert root.conditions[2].field_path == "score"
        assert root.conditions[2].operator == DataSearchOperator.greater_than_or_equal
        assert root.conditions[2].value == 80

    def test_qb_any_combinator(self):
        """Test QB.any() to combine multiple conditions with OR."""
        from autocrud.query import QB

        # Basic any() with multiple conditions
        q = QB.any(
            QB["status"] == "draft", QB["status"] == "pending", QB["status"] == "review"
        )
        query = q.build()
        root = query.conditions[0]

        assert isinstance(root, DataSearchGroup)
        assert root.operator == DataSearchLogicOperator.or_op
        assert len(root.conditions) == 3

        # All should be status checks
        for i, expected_value in enumerate(["draft", "pending", "review"]):
            assert root.conditions[i].field_path == "status"
            assert root.conditions[i].operator == DataSearchOperator.equals
            assert root.conditions[i].value == expected_value

    def test_qb_all_single_condition(self):
        """Test QB.all() with single condition returns that condition."""
        from autocrud.query import QB

        q = QB.all(QB["age"] > 18)
        query = q.build()
        cond = query.conditions[0]

        # Should just return the single condition, not wrapped in a group
        assert cond.field_path == "age"
        assert cond.operator == DataSearchOperator.greater_than
        assert cond.value == 18

    def test_qb_all_any_combined(self):
        """Test combining QB.all() and QB.any() for complex logic."""
        from autocrud.query import QB

        # (age > 18 AND score >= 80) OR (status == "premium")
        q = QB.any(QB.all(QB["age"] > 18, QB["score"] >= 80), QB["status"] == "premium")
        query = q.build()
        root = query.conditions[0]

        assert root.operator == DataSearchLogicOperator.or_op
        assert len(root.conditions) == 2

        # First: AND group (age > 18 AND score >= 80)
        and_group = root.conditions[0]
        assert and_group.operator == DataSearchLogicOperator.and_op
        assert len(and_group.conditions) == 2

        # Second: status == "premium"
        assert root.conditions[1].field_path == "status"
        assert root.conditions[1].operator == DataSearchOperator.equals

    def test_qb_all_any_with_normal_operators(self):
        """Test QB.all() and QB.any() combined with & and | operators."""
        from autocrud.query import QB

        # QB.all(...) & other_condition
        q = QB.all(QB["age"] > 18, QB["score"] >= 80) & (QB["verified"] == "yes")
        query = q.build()
        root = query.conditions[0]

        assert root.operator == DataSearchLogicOperator.and_op
        assert len(root.conditions) == 2

        # First is the all() group
        all_group = root.conditions[0]
        assert all_group.operator == DataSearchLogicOperator.and_op

        # Second is verified == "yes"
        assert root.conditions[1].field_path == "verified"

    def test_sorting_transformation(self):
        """Test sorting transformation for both meta and data fields."""
        # Meta field sort
        creation_time_sort = QB.created_time().desc()
        query = QB["x"].eq(1).sort(creation_time_sort).build()

        s1 = query.sorts[0]
        assert s1.key == ResourceMetaSortKey.created_time
        assert s1.direction == ResourceMetaSortDirection.descending

        # Data field sort
        age_sort = QB["user.age"].asc()
        query = QB["x"].eq(1).sort(age_sort).build()

        s2 = query.sorts[0]
        assert isinstance(s2, ResourceDataSearchSort)
        assert s2.field_path == "user.age"
        assert s2.direction == ResourceMetaSortDirection.ascending

    # QB["field"] syntax tests are covered in test_qb_getitem_* methods below

    def test_meta_attributes_staticmethods(self):
        """Test QB meta attribute static methods with proper typing."""
        # Test resource_id
        q = QB.resource_id().eq("abc-123")
        cond = q.build().conditions[0]
        assert cond.field_path == "resource_id"
        assert cond.operator == DataSearchOperator.equals

        # Test created_by with in_list
        q = QB.created_by() << ["user1", "user2", "admin"]
        cond = q.build().conditions[0]
        assert cond.field_path == "created_by"
        assert cond.operator == DataSearchOperator.in_list

        # Test created_time with datetime methods
        q = QB.created_time().today()
        query = q.build()
        cond = query.conditions[0]
        assert isinstance(cond, DataSearchGroup)
        assert cond.operator == DataSearchLogicOperator.and_op

        # Test updated_time with comparison
        import datetime as dt

        timestamp = dt.datetime(2024, 1, 1)
        q = QB.updated_time() >= timestamp
        cond = q.build().conditions[0]
        assert cond.field_path == "updated_time"
        assert cond.operator == DataSearchOperator.greater_than_or_equal

        # Test is_deleted
        q = QB.is_deleted() == False  # noqa: E712
        cond = q.build().conditions[0]
        assert cond.field_path == "is_deleted"
        assert cond.value is False

        # Test schema_version
        q = QB.schema_version().eq("v2")
        cond = q.build().conditions[0]
        assert cond.field_path == "schema_version"

        # Test revision_id (current_revision_id)
        q = QB.revision_id().eq("rev-456")
        cond = q.build().conditions[0]
        assert cond.field_path == "current_revision_id"

        # Test total_revision_count
        q = QB.total_revision_count() > 5
        cond = q.build().conditions[0]
        assert cond.field_path == "total_revision_count"
        assert cond.operator == DataSearchOperator.greater_than

    def test_meta_vs_data_fields(self):
        """Test that meta and data fields can be used together."""
        # Combine meta attribute with data field
        q = (QB.created_by().eq("admin")) & (QB["status"].eq("active"))
        query = q.build()
        group = query.conditions[0]

        assert group.operator == DataSearchLogicOperator.and_op
        assert len(group.conditions) == 2

        # First: created_by (meta)
        assert group.conditions[0].field_path == "created_by"

        # Second: status (data)
        assert group.conditions[1].field_path == "status"

    def test_qb_getitem_basic(self):
        """Test QB['field'] syntax for accessing data fields."""
        q1 = QB["name"].eq("Alice")
        q2 = QB["name"].eq("Alice")

        cond1 = q1.build().conditions[0]
        cond2 = q2.build().conditions[0]

        assert cond1.field_path == cond2.field_path == "name"
        assert cond1.operator == cond2.operator
        assert cond1.value == cond2.value

    def test_qb_getitem_reserved_keywords(self):
        """Test QB['keyword'] for Python reserved keywords."""
        # Test various reserved keywords
        keywords = ["class", "import", "return", "for", "while", "def"]

        for keyword in keywords:
            q1 = QB[keyword].eq("value")
            q2 = QB[keyword].eq("value")

            cond1 = q1.build().conditions[0]
            cond2 = q2.build().conditions[0]

            assert cond1.field_path == cond2.field_path == keyword

    def test_qb_getitem_special_chars(self):
        """Test QB['field'] with special characters."""
        # Hyphen
        q = QB["field-name"].eq("value")
        cond = q.build().conditions[0]
        assert cond.field_path == "field-name"

        # Space
        q = QB["field name"].contains("test")
        cond = q.build().conditions[0]
        assert cond.field_path == "field name"

        # Dots
        q = QB["user.email"].starts_with("test")
        cond = q.build().conditions[0]
        assert cond.field_path == "user.email"

        # Numbers
        q = QB["field123"].gt(10)
        cond = q.build().conditions[0]
        assert cond.field_path == "field123"

    def test_qb_getitem_complex_query(self):
        """Test QB['field'] in complex queries."""
        q = (QB["status"].eq("active") & QB["age"].gt(18)) | QB["role"].eq("admin")
        query = q.build()

        group = query.conditions[0]
        assert isinstance(group, DataSearchGroup)
        assert group.operator == DataSearchLogicOperator.or_op

    def test_qb_getitem_with_operators(self):
        """Test QB['field'] with all operators."""
        # Comparison operators
        assert QB["age"].eq(30).build().conditions[0].field_path == "age"
        assert QB["age"].ne(30).build().conditions[0].field_path == "age"
        assert QB["age"].gt(30).build().conditions[0].field_path == "age"
        assert QB["age"].gte(30).build().conditions[0].field_path == "age"
        assert QB["age"].lt(30).build().conditions[0].field_path == "age"
        assert QB["age"].lte(30).build().conditions[0].field_path == "age"

        # String operators
        assert QB["name"].contains("test").build().conditions[0].field_path == "name"
        assert (
            QB["email"].starts_with("admin").build().conditions[0].field_path == "email"
        )
        assert QB["file"].ends_with(".txt").build().conditions[0].field_path == "file"

        # Dunder operators
        assert (QB["age"] == 30).build().conditions[0].field_path == "age"
        assert (QB["age"] > 30).build().conditions[0].field_path == "age"
        assert (QB["status"] << ["a", "b"]).build().conditions[0].field_path == "status"
        assert (QB["desc"] >> "test").build().conditions[0].field_path == "desc"

    def test_qb_getitem_with_sorting(self):
        """Test QB['field'] with sorting."""
        q = QB["status"].eq("active").sort(QB["age"].desc())
        query = q.build()

        assert query.sorts is not UNSET
        assert len(query.sorts) == 1
        sort = query.sorts[0]
        assert sort.field_path == "age"
        assert sort.direction == ResourceMetaSortDirection.descending

    def test_qb_getitem_equivalence(self):
        """Test QB['field'] is exactly equivalent to QB['field']."""
        fields = ["name", "age", "user.email", "class", "field-name", "123"]

        for field_name in fields:
            # Test that both create the same Field
            f1 = QB[field_name]
            f2 = QB[field_name]

            assert f1.name == f2.name == field_name
            assert isinstance(f1, type(f2))

    def test_field_method_in_complex_query(self):
        """Test QB[) in complex queries with AND/OR."""
        q = (QB["class"].eq("A") & QB["normal_field"].gt(10)) | QB["import"].in_(
            ["os", "sys"]
        )
        query = q.build()

        root = query.conditions[0]
        assert root.operator == DataSearchLogicOperator.or_op

        # Left: (class == "A" AND normal_field > 10)
        left = root.conditions[0]
        assert left.operator == DataSearchLogicOperator.and_op
        assert left.conditions[0].field_path == "class"
        assert left.conditions[1].field_path == "normal_field"

        # Right: import in ["os", "sys"]
        right = root.conditions[1]
        assert right.field_path == "import"
        assert right.operator == DataSearchOperator.in_list

    def test_field_method_with_sorting(self):
        """Test QB[) with sorting and pagination."""
        q = (
            QB["sort-by"]
            .eq("priority")
            .sort(QB["created-at"].desc())
            .sort(QB["priority-level"].asc())
            .limit(10)
            .offset(5)
        )
        query = q.build()

        # Check condition
        cond = query.conditions[0]
        assert cond.field_path == "sort-by"

        # Check sorts
        assert len(query.sorts) == 2
        s1 = query.sorts[0]
        assert isinstance(s1, ResourceDataSearchSort)
        assert s1.field_path == "created-at"
        assert s1.direction == ResourceMetaSortDirection.descending

        s2 = query.sorts[1]
        assert s2.field_path == "priority-level"
        assert s2.direction == ResourceMetaSortDirection.ascending

        # Check pagination
        assert query.limit == 10
        assert query.offset == 5

    def test_field_method_all_operators(self):
        """Test that QB[) works with all operators."""
        field = QB["test-field"]

        # Test a few key operators
        assert field.eq(1).build().conditions[0].operator == DataSearchOperator.equals
        assert (
            field.ne(1).build().conditions[0].operator == DataSearchOperator.not_equals
        )
        assert (
            field.gt(1).build().conditions[0].operator
            == DataSearchOperator.greater_than
        )
        assert (
            field.in_([1, 2]).build().conditions[0].operator
            == DataSearchOperator.in_list
        )
        assert (
            field.regex(".*").build().conditions[0].operator == DataSearchOperator.regex
        )
        assert (
            field.is_null().build().conditions[0].operator == DataSearchOperator.is_null
        )

    def test_field_dunder_methods(self):
        """Test Field dunder methods for Pythonic syntax."""
        # Test ==
        q = QB["name"] == "Alice"
        cond = q.build().conditions[0]
        assert cond.field_path == "name"
        assert cond.operator == DataSearchOperator.equals
        assert cond.value == "Alice"

        # Test !=
        q = QB["age"] != 30
        cond = q.build().conditions[0]
        assert cond.operator == DataSearchOperator.not_equals
        assert cond.value == 30

        # Test >
        q = QB["score"] > 80
        cond = q.build().conditions[0]
        assert cond.operator == DataSearchOperator.greater_than
        assert cond.value == 80

        # Test >=
        q = QB["score"] >= 90
        cond = q.build().conditions[0]
        assert cond.operator == DataSearchOperator.greater_than_or_equal
        assert cond.value == 90

        # Test <
        q = QB["age"] < 18
        cond = q.build().conditions[0]
        assert cond.operator == DataSearchOperator.less_than
        assert cond.value == 18

        # Test <=
        q = QB["age"] <= 65
        cond = q.build().conditions[0]
        assert cond.operator == DataSearchOperator.less_than_or_equal
        assert cond.value == 65

    def test_field_dunder_methods_equivalence(self):
        """Verify dunder methods produce same results as named methods."""
        # == vs eq
        q1 = QB["name"] == "test"
        q2 = QB["name"].eq("test")
        assert q1.build().conditions[0].operator == q2.build().conditions[0].operator

        # != vs ne
        q1 = QB["age"] != 30
        q2 = QB["age"].ne(30)
        assert q1.build().conditions[0].operator == q2.build().conditions[0].operator

        # > vs gt
        q1 = QB["score"] > 80
        q2 = QB["score"].gt(80)
        assert q1.build().conditions[0].operator == q2.build().conditions[0].operator

        # >= vs gte
        q1 = QB["score"] >= 90
        q2 = QB["score"].gte(90)
        assert q1.build().conditions[0].operator == q2.build().conditions[0].operator

        # < vs lt
        q1 = QB["age"] < 18
        q2 = QB["age"].lt(18)
        assert q1.build().conditions[0].operator == q2.build().conditions[0].operator

        # <= vs lte
        q1 = QB["age"] <= 65
        q2 = QB["age"].lte(65)
        assert q1.build().conditions[0].operator == q2.build().conditions[0].operator

    def test_field_dunder_methods_in_complex_query(self):
        """Test dunder methods in complex queries with AND/OR."""
        # (name == "Alice" AND age > 30) OR (score >= 90 AND status != "inactive")
        q = ((QB["name"] == "Alice") & (QB["age"] > 30)) | (
            (QB["score"] >= 90) & (QB["status"] != "inactive")
        )
        query = q.build()

        root = query.conditions[0]
        assert root.operator == DataSearchLogicOperator.or_op
        assert len(root.conditions) == 2

        # Left side: name == "Alice" AND age > 30
        left = root.conditions[0]
        assert left.operator == DataSearchLogicOperator.and_op
        assert left.conditions[0].field_path == "name"
        assert left.conditions[0].operator == DataSearchOperator.equals
        assert left.conditions[1].field_path == "age"
        assert left.conditions[1].operator == DataSearchOperator.greater_than

        # Right side: score >= 90 AND status != "inactive"
        right = root.conditions[1]
        assert right.operator == DataSearchLogicOperator.and_op
        assert right.conditions[0].field_path == "score"
        assert right.conditions[0].operator == DataSearchOperator.greater_than_or_equal
        assert right.conditions[1].field_path == "status"
        assert right.conditions[1].operator == DataSearchOperator.not_equals

    def test_field_dunder_methods_with_field_method(self):
        """Test dunder methods work with QB[) for special names."""
        # Reserved keyword with dunder method
        q = QB["class"] == "A"
        cond = q.build().conditions[0]
        assert cond.field_path == "class"
        assert cond.operator == DataSearchOperator.equals

        # Special character with comparison operators
        q = (QB["priority-level"] >= 5) & (QB["max-score"] <= 100)
        query = q.build()
        group = query.conditions[0]
        assert group.operator == DataSearchLogicOperator.and_op
        assert group.conditions[0].field_path == "priority-level"
        assert group.conditions[0].operator == DataSearchOperator.greater_than_or_equal
        assert group.conditions[1].field_path == "max-score"
        assert group.conditions[1].operator == DataSearchOperator.less_than_or_equal

    def test_field_dunder_methods_practical_example(self):
        """Test practical query using dunder methods."""
        # Find users: age between 18-65, score > 80, and name not "admin"
        q = (
            ((QB["age"] >= 18) & (QB["age"] <= 65))
            & (QB["score"] > 80)
            & (QB["name"] != "admin")
        )
        query = q.build()

        # Verify structure
        root = query.conditions[0]
        assert root.operator == DataSearchLogicOperator.and_op

        # This creates nested AND groups
        # The exact structure depends on evaluation order, but all conditions should be present
        # Let's just verify the query builds successfully
        assert query.conditions is not UNSET

    def test_field_advanced_dunder_methods(self):
        """Test advanced dunder methods: %, <<, >>, ~"""
        # Test % for regex
        q = QB["email"] % r".*@example\.com"
        cond = q.build().conditions[0]
        assert cond.field_path == "email"
        assert cond.operator == DataSearchOperator.regex
        assert cond.value == r".*@example\.com"

        # Test << for in_list
        q = QB["status"] << ["active", "pending", "approved"]
        cond = q.build().conditions[0]
        assert cond.field_path == "status"
        assert cond.operator == DataSearchOperator.in_list
        assert cond.value == ["active", "pending", "approved"]

        # Test >> for contains
        q = QB["description"] >> "important"
        cond = q.build().conditions[0]
        assert cond.field_path == "description"
        assert cond.operator == DataSearchOperator.contains
        assert cond.value == "important"

        # Test ~ for is_falsy (NOT of is_truthy)
        q = ~QB["comment"]
        cond = q.build().conditions[0]
        assert isinstance(cond, DataSearchGroup)
        assert cond.operator == DataSearchLogicOperator.not_op
        assert len(cond.conditions) == 1

        # Inside NOT is is_truthy (AND group)
        inner = cond.conditions[0]
        assert isinstance(inner, DataSearchGroup)
        assert inner.operator == DataSearchLogicOperator.and_op
        assert len(inner.conditions) == 5  # not null, not false, not 0, not "", not []

    def test_field_advanced_dunder_methods_equivalence(self):
        """Verify advanced dunder methods produce same results as named methods."""
        # % vs regex
        q1 = QB["name"] % ".*test.*"
        q2 = QB["name"].regex(".*test.*")
        assert q1.build().conditions[0].operator == q2.build().conditions[0].operator

        # << vs in_
        q1 = QB["status"] << [1, 2, 3]
        q2 = QB["status"].in_([1, 2, 3])
        assert q1.build().conditions[0].operator == q2.build().conditions[0].operator

        # >> vs contains
        q1 = QB["text"] >> "substring"
        q2 = QB["text"].contains("substring")
        assert q1.build().conditions[0].operator == q2.build().conditions[0].operator

        # ~ vs is_falsy()
        q1 = ~QB["field1"]
        q2 = QB["field1"].is_falsy()
        # Both should produce NOT groups
        cond1 = q1.build().conditions[0]
        cond2 = q2.build().conditions[0]
        assert isinstance(cond1, DataSearchGroup)
        assert isinstance(cond2, DataSearchGroup)
        assert cond1.operator == cond2.operator == DataSearchLogicOperator.not_op
        assert len(cond1.conditions) == len(cond2.conditions) == 1

        # Inside NOT should be is_truthy (AND group with 5 conditions)
        assert cond1.conditions[0].operator == DataSearchLogicOperator.and_op
        assert len(cond1.conditions[0].conditions) == 5

    def test_field_advanced_dunder_methods_in_complex_query(self):
        """Test advanced dunder methods in complex queries."""
        # Find records: email matches pattern, status in list, description contains keyword, not deleted
        q = (
            (QB["email"] % r".*@(gmail|yahoo)\.com")
            & (QB["status"] << ["active", "verified"])
            & (QB["description"] >> "premium")
            & ~QB["deleted_at"]
        )
        query = q.build()

        root = query.conditions[0]
        assert root.operator == DataSearchLogicOperator.and_op

        # Verify all conditions are present
        # The structure is nested, but we can check it builds successfully
        assert query.conditions is not UNSET

    def test_field_advanced_dunder_with_field_method(self):
        """Test advanced dunder methods work with QB[) for special names."""
        # Test with special field names
        q = QB["email-address"] % r".*@test\.com"
        cond = q.build().conditions[0]
        assert cond.field_path == "email-address"
        assert cond.operator == DataSearchOperator.regex

        q = QB["user-status"] << ["active", "pending"]
        cond = q.build().conditions[0]
        assert cond.field_path == "user-status"
        assert cond.operator == DataSearchOperator.in_list

        q = QB["full-name"] >> "John"
        cond = q.build().conditions[0]
        assert cond.field_path == "full-name"
        assert cond.operator == DataSearchOperator.contains

        q = ~QB["comment"]
        cond = q.build().conditions[0]
        assert isinstance(cond, DataSearchGroup)
        assert cond.operator == DataSearchLogicOperator.not_op
        assert len(cond.conditions) == 1
        # Inside NOT is is_truthy (AND group)
        assert cond.conditions[0].operator == DataSearchLogicOperator.and_op

    def test_field_all_dunder_methods_combined(self):
        """Test combining all dunder methods in a complex real-world query."""
        # Complex query:
        # - age between 18-65
        # - email matches pattern
        # - role in allowed list
        # - bio contains keyword
        # - not deleted
        # - score > 80
        q = (
            ((QB["age"] >= 18) & (QB["age"] <= 65))
            & (QB["email"] % r".*@company\.com")
            & (QB["role"] << ["admin", "moderator", "user"])
            & (QB["bio"] >> "experienced")
            & ~QB["deleted_at"]
            & (QB["score"] > 80)
        )
        query = q.build()

        # Verify query builds successfully with all operators
        assert query.conditions is not UNSET
        root = query.conditions[0]
        assert root.operator == DataSearchLogicOperator.and_op

    def test_one_of_alias(self):
        """Test one_of() as Pythonic alias for in_()."""
        # one_of() should be equivalent to in_()
        q1 = QB["status"].one_of(["active", "pending", "approved"])
        q2 = QB["status"].in_(["active", "pending", "approved"])

        query1 = q1.build()
        query2 = q2.build()

        cond1 = query1.conditions[0]
        cond2 = query2.conditions[0]

        assert cond1.field_path == cond2.field_path == "status"
        assert cond1.operator == cond2.operator == DataSearchOperator.in_list
        assert cond1.value == cond2.value == ["active", "pending", "approved"]

    def test_case_insensitive_methods(self):
        """Test icontains(), istarts_with(), iends_with()."""
        # icontains
        q = QB["name"].icontains("alice")
        cond = q.build().conditions[0]
        assert cond.field_path == "name"
        assert cond.operator == DataSearchOperator.regex
        assert "(?i)" in cond.value  # Case-insensitive flag
        assert "alice" in cond.value

        # istarts_with
        q = QB["email"].istarts_with("admin")
        cond = q.build().conditions[0]
        assert cond.field_path == "email"
        assert cond.operator == DataSearchOperator.regex
        assert "(?i)" in cond.value
        assert "^" in cond.value  # Start anchor
        assert "admin" in cond.value

        # iends_with
        q = QB["domain"].iends_with("@gmail.com")
        cond = q.build().conditions[0]
        assert cond.field_path == "domain"
        assert cond.operator == DataSearchOperator.regex
        assert "(?i)" in cond.value
        assert "$" in cond.value  # End anchor

    def test_negative_string_methods(self):
        """Test not_contains(), not_starts_with(), not_ends_with()."""
        # not_contains
        q = QB["description"].not_contains("spam")
        query = q.build()
        root = query.conditions[0]
        assert root.operator == DataSearchLogicOperator.not_op
        assert len(root.conditions) == 1
        inner = root.conditions[0]
        assert inner.field_path == "description"
        assert inner.operator == DataSearchOperator.contains
        assert inner.value == "spam"

        # not_starts_with
        q = QB["email"].not_starts_with("spam")
        query = q.build()
        root = query.conditions[0]
        assert root.operator == DataSearchLogicOperator.not_op
        inner = root.conditions[0]
        assert inner.operator == DataSearchOperator.starts_with

        # not_ends_with
        q = QB["filename"].not_ends_with(".tmp")
        query = q.build()
        root = query.conditions[0]
        assert root.operator == DataSearchLogicOperator.not_op
        inner = root.conditions[0]
        assert inner.operator == DataSearchOperator.ends_with

    def test_is_empty(self):
        """Test is_empty() - checks for empty string or null."""
        q = QB["description"].is_empty()
        query = q.build()
        root = query.conditions[0]

        assert isinstance(root, DataSearchGroup)
        assert root.operator == DataSearchLogicOperator.or_op
        assert len(root.conditions) == 2

        # First: equals ""
        cond1 = root.conditions[0]
        assert cond1.field_path == "description"
        assert cond1.operator == DataSearchOperator.equals
        assert cond1.value == ""

        # Second: is_null
        cond2 = root.conditions[1]
        assert cond2.field_path == "description"
        assert cond2.operator == DataSearchOperator.is_null
        assert cond2.value is True

    def test_is_blank(self):
        """Test is_blank() - checks for empty, null, or whitespace-only."""
        q = QB["name"].is_blank()
        query = q.build()
        root = query.conditions[0]

        assert isinstance(root, DataSearchGroup)
        assert root.operator == DataSearchLogicOperator.or_op
        assert len(root.conditions) == 3

        # First: equals ""
        assert root.conditions[0].operator == DataSearchOperator.equals
        assert root.conditions[0].value == ""

        # Second: is_null
        assert root.conditions[1].operator == DataSearchOperator.is_null

        # Third: regex for whitespace
        assert root.conditions[2].operator == DataSearchOperator.regex
        assert root.conditions[2].value == r"^\s*$"

    def test_match_alias(self):
        """Test match() as alias for regex()."""
        # match() should be equivalent to regex()
        q1 = QB["email"].match(r".*@gmail\.com$")
        q2 = QB["email"].regex(r".*@gmail\.com$")

        query1 = q1.build()
        query2 = q2.build()

        cond1 = query1.conditions[0]
        cond2 = query2.conditions[0]

        assert cond1.field_path == cond2.field_path == "email"
        assert cond1.operator == cond2.operator == DataSearchOperator.regex
        assert cond1.value == cond2.value == r".*@gmail\.com$"

    def test_sort_with_string_ascending(self):
        """Test sort() with string parameter for ascending order."""
        # Without prefix (default ascending)
        q1 = QB["age"].gt(0).sort("name")
        query1 = q1.build()
        assert len(query1.sorts) == 1
        assert query1.sorts[0].field_path == "name"
        assert query1.sorts[0].direction == ResourceMetaSortDirection.ascending

        # With + prefix (explicit ascending)
        q2 = QB["age"].gt(0).sort("+age")
        query2 = q2.build()
        assert len(query2.sorts) == 1
        assert query2.sorts[0].field_path == "age"
        assert query2.sorts[0].direction == ResourceMetaSortDirection.ascending

    def test_sort_with_string_descending(self):
        """Test sort() with string parameter for descending order."""
        q = QB["age"].gt(0).sort("-created_time")
        query = q.build()
        assert len(query.sorts) == 1
        assert query.sorts[0].key == ResourceMetaSortKey.created_time
        assert query.sorts[0].direction == ResourceMetaSortDirection.descending

    def test_sort_with_multiple_strings(self):
        """Test sort() with multiple string parameters."""
        q = QB["age"].gt(0).sort("-created_time", "+name", "age")
        query = q.build()
        assert len(query.sorts) == 3

        # First: created_time descending (meta field)
        assert query.sorts[0].key == ResourceMetaSortKey.created_time
        assert query.sorts[0].direction == ResourceMetaSortDirection.descending

        # Second: name ascending (data field)
        assert query.sorts[1].field_path == "name"
        assert query.sorts[1].direction == ResourceMetaSortDirection.ascending

        # Third: age ascending (data field, no prefix)
        assert query.sorts[2].field_path == "age"
        assert query.sorts[2].direction == ResourceMetaSortDirection.ascending

    def test_sort_mixed_string_and_objects(self):
        """Test sort() with mix of strings and sort objects."""
        q = QB["age"].gt(0).sort("-name", QB.created_time().desc(), "+age")
        query = q.build()
        assert len(query.sorts) == 3

        # First: name descending (string)
        assert query.sorts[0].field_path == "name"
        assert query.sorts[0].direction == ResourceMetaSortDirection.descending

        # Second: created_time descending (object)
        assert query.sorts[1].key == ResourceMetaSortKey.created_time
        assert query.sorts[1].direction == ResourceMetaSortDirection.descending

        # Third: age ascending (string)
        assert query.sorts[2].field_path == "age"
        assert query.sorts[2].direction == ResourceMetaSortDirection.ascending

    def test_order_by_alias(self):
        """Test order_by() as alias for sort()."""
        # order_by() should work the same as sort()
        q1 = QB["age"].gt(0).order_by("-created_time", "+name")
        q2 = QB["age"].gt(0).sort("-created_time", "+name")

        query1 = q1.build()
        query2 = q2.build()

        assert len(query1.sorts) == len(query2.sorts) == 2
        assert query1.sorts[0].key == query2.sorts[0].key
        assert query1.sorts[0].direction == query2.sorts[0].direction
        assert query1.sorts[1].field_path == query2.sorts[1].field_path
        assert query1.sorts[1].direction == query2.sorts[1].direction

    def test_order_by_with_objects(self):
        """Test order_by() with sort objects."""
        q = (
            QB["status"]
            .eq("active")
            .order_by(QB.created_time().desc(), QB["age"].asc())
        )
        query = q.build()
        assert len(query.sorts) == 2
        assert query.sorts[0].key == ResourceMetaSortKey.created_time
        assert query.sorts[1].field_path == "age"

    def test_convenience_methods_combined(self):
        """Test combining new convenience methods in real query."""
        # Find users: name not empty, email contains company domain (case-insensitive),
        # status is one of allowed values, description does not contain spam
        q = (
            ~QB["name"].is_empty()
            & QB["email"].icontains("@company.com")
            & QB["status"].one_of(["active", "verified", "premium"])
            & QB["description"].not_contains("spam")
        )
        query = q.build()

        # Verify query builds successfully
        assert query.conditions is not UNSET
        root = query.conditions[0]
        assert root.operator == DataSearchLogicOperator.and_op

    def test_case_insensitive_special_chars(self):
        """Test that icontains/istarts_with/iends_with properly escape special regex chars."""
        # Test with regex special characters
        q = QB["text"].icontains("$100.00")
        cond = q.build().conditions[0]
        # $ and . should be escaped
        assert r"\$" in cond.value or "\\$" in cond.value
        assert r"\." in cond.value or "\\." in cond.value

        q = QB["pattern"].istarts_with("test[123]")
        cond = q.build().conditions[0]
        # [ and ] should be escaped
        assert r"\[" in cond.value or "\\[" in cond.value

    def test_invert_operator_practical_examples(self):
        """Test ~ operator in practical use cases."""
        # Case 1: Find records with empty optional fields
        q = (QB["status"] == "active") & ~QB["comment"]
        query = q.build()
        root = query.conditions[0]
        assert root.operator == DataSearchLogicOperator.and_op

        # Right side should be is_falsy (NOT group)
        falsy_group = root.conditions[1]
        assert isinstance(falsy_group, DataSearchGroup)
        assert falsy_group.operator == DataSearchLogicOperator.not_op
        assert len(falsy_group.conditions) == 1
        # Inside NOT is is_truthy (AND group)
        assert falsy_group.conditions[0].operator == DataSearchLogicOperator.and_op

        # Case 2: Complex query with multiple falsy checks
        q = QB.all(
            QB["status"] == "published",
            QB["score"] > 50,
            ~QB["archived"],  # Not archived (falsy)
            ~QB["deleted"],  # Not deleted (falsy)
        )
        query = q.build()
        root = query.conditions[0]
        assert root.operator == DataSearchLogicOperator.and_op
        assert len(root.conditions) == 4

    def test_field_as_truthy_condition(self):
        """Test that Field can be used directly as is_truthy() condition."""
        # Case 1: Single field acts as is_truthy()
        q = QB["verified"]
        cond = q.build().conditions[0]
        assert isinstance(cond, DataSearchGroup)
        assert cond.operator == DataSearchLogicOperator.and_op
        assert len(cond.conditions) == 5  # not null, not false, not 0, not "", not []

        # Case 2: Field in AND operation
        q = QB["verified"] & (QB["status"] == "active")
        query = q.build()
        root = query.conditions[0]
        assert root.operator == DataSearchLogicOperator.and_op
        assert len(root.conditions) == 2

        # First should be verified (is_truthy)
        verified_cond = root.conditions[0]
        assert isinstance(verified_cond, DataSearchGroup)
        assert verified_cond.operator == DataSearchLogicOperator.and_op

        # Second should be status == "active"
        status_cond = root.conditions[1]
        assert status_cond.field_path == "status"
        assert status_cond.operator == DataSearchOperator.equals

    def test_field_as_truthy_with_negation(self):
        """Test ~Field produces is_falsy() as expected."""
        # ~Field should give is_falsy() which is NOT(is_truthy)
        q = ~QB["optional"]
        cond = q.build().conditions[0]
        assert isinstance(cond, DataSearchGroup)
        assert cond.operator == DataSearchLogicOperator.not_op
        assert len(cond.conditions) == 1

        # Inside NOT is is_truthy (AND group with 5 conditions)
        inner = cond.conditions[0]
        assert isinstance(inner, DataSearchGroup)
        assert inner.operator == DataSearchLogicOperator.and_op
        assert len(inner.conditions) == 5  # not null, not false, not 0, not "", not []

    def test_field_truthy_equivalence(self):
        """Test Field is equivalent to Field.is_truthy()."""
        # QB["foo"] should be same as QB["foo"].is_truthy()
        q1 = QB["name"]
        q2 = QB["name"].is_truthy()

        cond1 = q1.build().conditions[0]
        cond2 = q2.build().conditions[0]

        assert isinstance(cond1, DataSearchGroup)
        assert isinstance(cond2, DataSearchGroup)
        assert cond1.operator == cond2.operator == DataSearchLogicOperator.and_op
        assert len(cond1.conditions) == len(cond2.conditions) == 5

    def test_field_in_complex_logic(self):
        """Test Field as truthy in complex queries."""
        # (verified AND email) OR (admin AND active)
        # All four fields act as is_truthy()
        q = (QB["verified"] & QB["email"]) | (QB["admin"] & QB["active"])
        query = q.build()
        root = query.conditions[0]

        assert root.operator == DataSearchLogicOperator.or_op
        assert len(root.conditions) == 2

        # Left: verified AND email
        left = root.conditions[0]
        assert left.operator == DataSearchLogicOperator.and_op

        # Right: admin AND active
        right = root.conditions[1]
        assert right.operator == DataSearchLogicOperator.and_op


class TestResourceManagerWithQB:
    @pytest.fixture
    def resource_manager(self):
        meta_store = MemoryMetaStore()
        resource_store = MemoryResourceStore()
        storage = SimpleStorage(meta_store, resource_store)

        # Populate with some data
        now = dt.datetime.now(ZoneInfo("UTC"))

        metas = [
            ResourceMeta(
                resource_id="1",
                current_revision_id="1:1",
                total_revision_count=1,
                created_time=now,
                updated_time=now,
                created_by="user1",
                updated_by="user1",
                indexed_data={"name": "Alice", "age": 25, "dept": "Eng"},
            ),
            ResourceMeta(
                resource_id="2",
                current_revision_id="2:1",
                total_revision_count=1,
                created_time=now,
                updated_time=now,
                created_by="user2",
                updated_by="user2",
                indexed_data={"name": "Bob", "age": 30, "dept": "HR"},
            ),
            ResourceMeta(
                resource_id="3",
                current_revision_id="3:1",
                total_revision_count=1,
                created_time=now,
                updated_time=now,
                created_by="user3",
                updated_by="user3",
                indexed_data={"name": "Charlie", "age": 35, "dept": "Eng"},
            ),
            ResourceMeta(
                resource_id="4",
                current_revision_id="4:1",
                total_revision_count=1,
                created_time=now,
                updated_time=now,
                created_by="user4",
                updated_by="user4",
                indexed_data={"name": "David", "age": 40, "dept": "Sales"},
            ),
        ]

        for m in metas:
            meta_store[m.resource_id] = m

        return ResourceManager(
            resource_type=dict,
            storage=storage,
            indexed_fields=[
                IndexableField("name", str),
                IndexableField("age", int),
                IndexableField("dept", str),
            ],
        )

    def test_search_resources_qb(self, resource_manager: ResourceManager):
        # Search for Eng dept
        query = QB["dept"].eq("Eng")
        results = resource_manager.search_resources(query)
        assert len(results) == 2
        names = sorted([r.indexed_data["name"] for r in results])
        assert names == ["Alice", "Charlie"]

    def test_search_resources_qb_complex(self, resource_manager: ResourceManager):
        # Search for (Eng AND age > 30) OR (HR AND age >= 30)
        # Charlie (Eng, 35) -> Match
        # Alice (Eng, 25) -> No match
        # Bob (HR, 30) -> Match
        # David (Sales, 40) -> No match

        q = (QB["dept"].eq("Eng") & QB["age"].gt(30)) | (
            QB["dept"].eq("HR") & QB["age"].gte(30)
        )
        results = resource_manager.search_resources(q)
        assert len(results) == 2
        names = sorted([r.indexed_data["name"] for r in results])
        assert names == ["Bob", "Charlie"]

    def test_search_resources_qb_sort_limit(self, resource_manager: ResourceManager):
        # Search all, sort by age desc, limit 2
        q = QB["age"].gt(0).sort(QB["age"].desc()).limit(2)
        results = resource_manager.search_resources(q)
        assert len(results) == 2
        # Should be David (40) and Charlie (35)
        assert results[0].indexed_data["name"] == "David"
        assert results[1].indexed_data["name"] == "Charlie"

    def test_like_contains(self):
        """Test LIKE pattern %value% converts to contains (no underscore)."""
        q = QB["description"].like("%urgent%")
        query = q.build()
        condition = query.conditions[0]
        assert isinstance(condition, DataSearchCondition)
        assert condition.operator == DataSearchOperator.contains
        assert condition.value == "urgent"

    def test_like_starts_with(self):
        """Test LIKE pattern value% converts to starts_with (no underscore)."""
        q = QB["name"].like("Alice%")
        query = q.build()
        condition = query.conditions[0]
        assert isinstance(condition, DataSearchCondition)
        assert condition.operator == DataSearchOperator.starts_with
        assert condition.value == "Alice"

    def test_like_ends_with(self):
        """Test LIKE pattern %value converts to ends_with (no underscore)."""
        q = QB["email"].like("%@gmail.com")
        query = q.build()
        condition = query.conditions[0]
        assert isinstance(condition, DataSearchCondition)
        assert condition.operator == DataSearchOperator.ends_with
        assert condition.value == "@gmail.com"

    def test_like_with_underscore_uses_regex(self):
        """Test LIKE pattern with _ converts to regex."""
        q = QB["code"].like("A_C")
        query = q.build()
        condition = query.conditions[0]
        assert isinstance(condition, DataSearchCondition)
        assert condition.operator == DataSearchOperator.regex
        # Should convert _ to . and add anchors
        assert condition.value == "^A.C$"

    def test_like_contains_with_underscore_uses_regex(self):
        """Test LIKE pattern %val_ue% with _ uses regex, not contains."""
        q = QB["desc"].like("%ur_ent%")
        query = q.build()
        condition = query.conditions[0]
        assert isinstance(condition, DataSearchCondition)
        assert condition.operator == DataSearchOperator.regex
        # Should convert to regex with .* for % and . for _
        assert condition.value == "^.*ur.ent.*$"

    def test_like_starts_with_underscore_uses_regex(self):
        """Test LIKE pattern val_% with _ uses regex, not starts_with."""
        q = QB["name"].like("Ali_e%")
        query = q.build()
        condition = query.conditions[0]
        assert isinstance(condition, DataSearchCondition)
        assert condition.operator == DataSearchOperator.regex
        assert condition.value == "^Ali.e.*$"

    def test_like_ends_with_underscore_uses_regex(self):
        """Test LIKE pattern %val_e with _ uses regex, not ends_with."""
        q = QB["email"].like("%gma_l.com")
        query = q.build()
        condition = query.conditions[0]
        assert isinstance(condition, DataSearchCondition)
        assert condition.operator == DataSearchOperator.regex
        assert condition.value == "^.*gma.l\\.com$"

    def test_like_complex_pattern(self):
        """Test complex LIKE pattern with multiple % and _."""
        q = QB["path"].like("%file_%.txt")
        query = q.build()
        condition = query.conditions[0]
        assert isinstance(condition, DataSearchCondition)
        assert condition.operator == DataSearchOperator.regex
        # % -> .*, _ -> ., escape .txt
        assert condition.value == "^.*file..*\\.txt$"

    def test_like_percent_only(self):
        """Test LIKE pattern with only % (matches any)."""
        q = QB["value"].like("%")
        query = q.build()
        condition = query.conditions[0]
        # Single % should become regex .*
        assert condition.operator == DataSearchOperator.regex
        assert condition.value == "^.*$"

    def test_like_escape_special_chars(self):
        """Test LIKE properly escapes regex special characters."""
        # Pattern without % or _ should be treated as literal match with anchors
        q = QB["pattern"].like("file[0-9].txt")
        query = q.build()
        condition = query.conditions[0]
        assert condition.operator == DataSearchOperator.regex
        # Should escape [] and . in regex
        assert condition.value == r"^file\[0\-9\]\.txt$"

    def test_today_default_timezone(self):
        """Test today() uses local timezone by default."""
        import datetime as dt

        q = QB.created_time().today()
        query = q.build()
        group = query.conditions[0]
        assert isinstance(group, DataSearchGroup)
        assert group.operator == DataSearchLogicOperator.and_op

        # Should be between start and end of today
        cond_start = group.conditions[0]
        cond_end = group.conditions[1]
        assert cond_start.operator == DataSearchOperator.greater_than_or_equal
        assert cond_end.operator == DataSearchOperator.less_than_or_equal

        # Verify it's today's date
        start_val = cond_start.value
        end_val = cond_end.value
        assert isinstance(start_val, dt.datetime)
        assert isinstance(end_val, dt.datetime)
        assert start_val.hour == 0
        assert start_val.minute == 0
        assert end_val.hour == 23
        assert end_val.minute == 59

    def test_today_with_timezone(self):
        """Test today() with specific timezone."""
        from zoneinfo import ZoneInfo

        utc = ZoneInfo("UTC")
        q = QB.created_time().today(utc)
        query = q.build()
        group = query.conditions[0]

        cond_start = group.conditions[0]
        start_val = cond_start.value
        assert start_val.tzinfo == utc

    def test_this_week_default(self):
        """Test this_week() with default settings (Monday start)."""

        q = QB.created_time().this_week()
        query = q.build()
        group = query.conditions[0]
        assert isinstance(group, DataSearchGroup)
        assert group.operator == DataSearchLogicOperator.and_op

        cond_start = group.conditions[0]
        cond_end = group.conditions[1]
        start_val = cond_start.value
        end_val = cond_end.value

        # Start should be Monday 00:00:00
        assert start_val.weekday() == 0  # Monday
        assert start_val.hour == 0
        assert start_val.minute == 0

        # End should be Sunday 23:59:59
        assert end_val.weekday() == 6  # Sunday
        assert end_val.hour == 23
        assert end_val.minute == 59

    def test_this_week_custom_start(self):
        """Test this_week() with custom week start (Sunday)."""
        q = QB.created_time().this_week(week_start=6)
        query = q.build()
        group = query.conditions[0]

        cond_start = group.conditions[0]
        cond_end = group.conditions[1]
        start_val = cond_start.value
        end_val = cond_end.value

        # Start should be Sunday
        assert start_val.weekday() == 6  # Sunday
        # End should be Saturday (6 days later)
        assert end_val.weekday() == 5  # Saturday

    def test_this_week_with_timezone(self):
        """Test this_week() with specific timezone."""
        from zoneinfo import ZoneInfo

        taipei = ZoneInfo("Asia/Taipei")
        q = QB.created_time().this_week(taipei)
        query = q.build()
        group = query.conditions[0]

        cond_start = group.conditions[0]
        start_val = cond_start.value
        assert start_val.tzinfo == taipei

    def test_last_n_days(self):
        """Test last_n_days() for N=7."""
        import datetime as dt

        q = QB.created_time().last_n_days(7)
        query = q.build()
        condition = query.conditions[0]

        assert condition.operator == DataSearchOperator.greater_than_or_equal
        start_val = condition.value
        assert isinstance(start_val, dt.datetime)

        # Should be 7 days ago at 00:00:00
        assert start_val.hour == 0
        assert start_val.minute == 0
        assert start_val.second == 0

        # Verify it's approximately 6 days before today (7 days inclusive)
        now = dt.datetime.now().astimezone()
        days_diff = (now.date() - start_val.date()).days
        assert days_diff == 6  # 7 days inclusive means start from 6 days ago

    def test_last_n_days_with_timezone(self):
        """Test last_n_days() with specific timezone."""
        from zoneinfo import ZoneInfo

        utc = ZoneInfo("UTC")
        q = QB.created_time().last_n_days(30, utc)
        query = q.build()
        condition = query.conditions[0]

        start_val = condition.value
        assert start_val.tzinfo == utc

    def test_last_n_days_single_day(self):
        """Test last_n_days(1) means today only."""
        import datetime as dt

        q = QB.created_time().last_n_days(1)
        query = q.build()
        condition = query.conditions[0]

        start_val = condition.value
        now = dt.datetime.now().astimezone()

        # Should be today at 00:00:00
        assert start_val.date() == now.date()
        assert start_val.hour == 0
        assert start_val.minute == 0

    def test_datetime_methods_combined(self):
        """Test combining datetime methods with other conditions."""
        q = QB.created_time().last_n_days(7) & QB["status"].eq("active")
        query = q.build()

        group = query.conditions[0]
        assert isinstance(group, DataSearchGroup)
        assert group.operator == DataSearchLogicOperator.and_op
        assert len(group.conditions) == 2

    def test_datetime_methods_or_logic(self):
        """Test OR logic with datetime methods."""
        q = QB.created_time().today() | QB.updated_time().this_week()
        query = q.build()

        group = query.conditions[0]
        assert isinstance(group, DataSearchGroup)
        assert group.operator == DataSearchLogicOperator.or_op

    def test_today_with_int_offset(self):
        """Test today() with integer UTC offset."""
        import datetime as dt

        q = QB.created_time().today(8)
        query = q.build()
        group = query.conditions[0]

        cond_start = group.conditions[0]
        start_val = cond_start.value
        assert isinstance(start_val, dt.datetime)
        # Should be UTC+8
        assert start_val.utcoffset() == dt.timedelta(hours=8)

    def test_today_with_str_offset_positive(self):
        """Test today() with string UTC offset '+8'."""
        import datetime as dt

        q = QB.created_time().today("+8")
        query = q.build()
        group = query.conditions[0]

        cond_start = group.conditions[0]
        start_val = cond_start.value
        # Should be UTC+8
        assert start_val.utcoffset() == dt.timedelta(hours=8)

    def test_today_with_str_offset_negative(self):
        """Test today() with string UTC offset '-4'."""
        import datetime as dt

        q = QB.created_time().today("-4")
        query = q.build()
        group = query.conditions[0]

        cond_start = group.conditions[0]
        start_val = cond_start.value
        # Should be UTC-4
        assert start_val.utcoffset() == dt.timedelta(hours=-4)

    def test_this_week_with_int_offset(self):
        """Test this_week() with integer UTC offset."""
        import datetime as dt

        q = QB.created_time().this_week(8)
        query = q.build()
        group = query.conditions[0]

        cond_start = group.conditions[0]
        start_val = cond_start.value
        # Should be UTC+8
        assert start_val.utcoffset() == dt.timedelta(hours=8)

    def test_this_week_with_str_offset(self):
        """Test this_week() with string UTC offset."""
        import datetime as dt

        q = QB.created_time().this_week("-5")
        query = q.build()
        group = query.conditions[0]

        cond_start = group.conditions[0]
        start_val = cond_start.value
        # Should be UTC-5
        assert start_val.utcoffset() == dt.timedelta(hours=-5)

    def test_last_n_days_with_int_offset(self):
        """Test last_n_days() with integer UTC offset."""
        import datetime as dt

        q = QB.created_time().last_n_days(7, 8)
        query = q.build()
        condition = query.conditions[0]

        start_val = condition.value
        # Should be UTC+8
        assert start_val.utcoffset() == dt.timedelta(hours=8)

    def test_last_n_days_with_str_offset(self):
        """Test last_n_days() with string UTC offset."""
        import datetime as dt

        q = QB.created_time().last_n_days(30, "+9")
        query = q.build()
        condition = query.conditions[0]

        start_val = condition.value
        # Should be UTC+9
        assert start_val.utcoffset() == dt.timedelta(hours=9)

    def test_timezone_offset_zero(self):
        """Test UTC offset of 0 (equivalent to UTC)."""
        import datetime as dt

        q = QB.created_time().today(0)
        query = q.build()
        group = query.conditions[0]

        cond_start = group.conditions[0]
        start_val = cond_start.value
        # Should be UTC (offset 0)
        assert start_val.utcoffset() == dt.timedelta(hours=0)

    def test_timezone_offset_combined_query(self):
        """Test combining offset-based timezone with other conditions."""
        q = QB.created_time().last_n_days(7, "+8") & QB["status"].eq("active")
        query = q.build()

        group = query.conditions[0]
        assert isinstance(group, DataSearchGroup)
        assert group.operator == DataSearchLogicOperator.and_op
        assert len(group.conditions) == 2

    def test_filter_method(self):
        """Test filter() method for chaining AND conditions."""
        q = QB["age"].gt(18).filter(QB["status"].eq("active"), QB["verified"].eq(True))
        query = q.build()
        root = query.conditions[0]

        assert isinstance(root, DataSearchGroup)
        assert root.operator == DataSearchLogicOperator.and_op
        # Should have nested AND structure
        assert len(root.conditions) == 2

    def test_exclude_method(self):
        """Test exclude() method for excluding conditions."""
        q = QB["status"].eq("active").exclude(QB["role"].eq("guest"))
        query = q.build()
        root = query.conditions[0]

        assert isinstance(root, DataSearchGroup)
        assert root.operator == DataSearchLogicOperator.and_op
        assert len(root.conditions) == 2

        # First: status == "active"
        assert root.conditions[0].field_path == "status"

        # Second: NOT(role == "guest")
        not_group = root.conditions[1]
        assert isinstance(not_group, DataSearchGroup)
        assert not_group.operator == DataSearchLogicOperator.not_op
        assert not_group.conditions[0].field_path == "role"

    def test_exclude_multiple_conditions(self):
        """Test exclude() with multiple conditions."""
        q = QB["age"].gt(18).exclude(QB["deleted"].eq(True), QB["banned"].eq(True))
        query = q.build()
        root = query.conditions[0]

        # Should AND all conditions (the original + negated ones)
        assert root.operator == DataSearchLogicOperator.and_op
        # Structure: (age > 18 AND NOT(deleted)) AND NOT(banned)
        # Root has 2 conditions: left group and right NOT
        assert len(root.conditions) == 2

    def test_in_range_alias(self):
        """Test in_range() as alias for between()."""
        q1 = QB["age"].in_range(18, 65)
        q2 = QB["age"].between(18, 65)

        query1 = q1.build()
        query2 = q2.build()

        cond1 = query1.conditions[0]
        cond2 = query2.conditions[0]

        assert isinstance(cond1, DataSearchGroup)
        assert isinstance(cond2, DataSearchGroup)
        assert cond1.operator == cond2.operator == DataSearchLogicOperator.and_op
        assert len(cond1.conditions) == len(cond2.conditions) == 2

    def test_is_not_null(self):
        """Test is_not_null() method."""
        q = QB["email"].is_not_null()
        query = q.build()
        cond = query.conditions[0]

        assert cond.field_path == "email"
        assert cond.operator == DataSearchOperator.is_null
        assert cond.value is False

    def test_has_value_alias(self):
        """Test has_value() as alias for is_not_null()."""
        q1 = QB["description"].has_value()
        q2 = QB["description"].is_not_null()

        query1 = q1.build()
        query2 = q2.build()

        cond1 = query1.conditions[0]
        cond2 = query2.conditions[0]

        assert cond1.field_path == cond2.field_path == "description"
        assert cond1.operator == cond2.operator == DataSearchOperator.is_null
        assert cond1.value == cond2.value is False

    def test_yesterday(self):
        """Test yesterday() datetime method."""
        import datetime as dt

        q = QB.created_time().yesterday()
        query = q.build()
        group = query.conditions[0]

        assert isinstance(group, DataSearchGroup)
        assert group.operator == DataSearchLogicOperator.and_op

        start_val = group.conditions[0].value
        end_val = group.conditions[1].value

        # Should be yesterday's date
        yesterday = dt.datetime.now().astimezone() - dt.timedelta(days=1)
        assert start_val.date() == yesterday.date()
        assert end_val.date() == yesterday.date()
        assert start_val.hour == 0
        assert end_val.hour == 23

    def test_this_month(self):
        """Test this_month() datetime method."""
        import datetime as dt

        q = QB.created_time().this_month()
        query = q.build()
        group = query.conditions[0]

        assert isinstance(group, DataSearchGroup)
        assert group.operator == DataSearchLogicOperator.and_op

        start_val = group.conditions[0].value
        end_val = group.conditions[1].value

        # Should be this month
        now = dt.datetime.now().astimezone()
        assert start_val.month == now.month
        assert start_val.year == now.year
        assert start_val.day == 1
        assert start_val.hour == 0

    def test_this_year(self):
        """Test this_year() datetime method."""
        import datetime as dt

        q = QB.created_time().this_year()
        query = q.build()
        group = query.conditions[0]

        assert isinstance(group, DataSearchGroup)
        assert group.operator == DataSearchLogicOperator.and_op

        start_val = group.conditions[0].value
        end_val = group.conditions[1].value

        # Should be this year
        now = dt.datetime.now().astimezone()
        assert start_val.year == now.year
        assert start_val.month == 1
        assert start_val.day == 1
        assert end_val.year == now.year
        assert end_val.month == 12
        assert end_val.day == 31

    def test_yesterday_with_timezone(self):
        """Test yesterday() with custom timezone."""
        import datetime as dt

        q = QB.created_time().yesterday("+8")
        query = q.build()
        group = query.conditions[0]

        start_val = group.conditions[0].value
        # Should be UTC+8
        assert start_val.utcoffset() == dt.timedelta(hours=8)

    def test_this_month_with_timezone(self):
        """Test this_month() with custom timezone."""
        import datetime as dt

        q = QB.created_time().this_month(-5)
        query = q.build()
        group = query.conditions[0]

        start_val = group.conditions[0].value
        # Should be UTC-5
        assert start_val.utcoffset() == dt.timedelta(hours=-5)

    def test_convenience_combined(self):
        """Test combining multiple new convenience methods."""
        q = (
            QB["age"]
            .in_range(18, 65)
            .filter(QB["email"].has_value(), QB["verified"].eq(True))
            .exclude(QB["deleted"].eq(True))
        )
        query = q.build()
        root = query.conditions[0]

        assert isinstance(root, DataSearchGroup)
        assert root.operator == DataSearchLogicOperator.and_op
        # Complex nested structure with all conditions properly combined
        # The exact count depends on nesting, but should have at least 2 main branches
        assert len(root.conditions) >= 2

    def test_is_true(self):
        """Test is_true() method for boolean True checks."""
        q = QB["verified"].is_true()
        query = q.build()
        cond = query.conditions[0]

        assert cond.field_path == "verified"
        assert cond.operator == DataSearchOperator.equals
        assert cond.value is True

    def test_is_false(self):
        """Test is_false() method for boolean False checks."""
        q = QB["deleted"].is_false()
        query = q.build()
        cond = query.conditions[0]

        assert cond.field_path == "deleted"
        assert cond.operator == DataSearchOperator.equals
        assert cond.value is False

    def test_is_true_is_false_combined(self):
        """Test combining is_true() and is_false()."""
        q = QB["active"].is_true() & QB["deleted"].is_false()
        query = q.build()
        group = query.conditions[0]

        assert group.operator == DataSearchLogicOperator.and_op
        assert len(group.conditions) == 2
        assert group.conditions[0].value is True
        assert group.conditions[1].value is False

    def test_is_truthy(self):
        """Test is_truthy() for truthy value checks."""
        q = QB["status"].is_truthy()
        query = q.build()
        root = query.conditions[0]

        # Should be a complex AND group checking != null, != false, != 0, != ""
        assert isinstance(root, DataSearchGroup)
        assert root.operator == DataSearchLogicOperator.and_op
        # Check not null condition exists
        assert root.conditions[0].operator == DataSearchOperator.is_null
        assert root.conditions[0].value is False

    def test_is_falsy(self):
        """Test is_falsy() for falsy value checks."""
        q = QB["optional"].is_falsy()
        query = q.build()
        root = query.conditions[0]

        # Should be NOT(is_truthy()), i.e., NOT group with inner AND group
        assert isinstance(root, DataSearchGroup)
        assert root.operator == DataSearchLogicOperator.not_op
        assert len(root.conditions) == 1

        # Inner condition should be the is_truthy AND group
        inner = root.conditions[0]
        assert isinstance(inner, DataSearchGroup)
        assert inner.operator == DataSearchLogicOperator.and_op
        assert len(inner.conditions) == 5

        # Check all truthy conditions (negated)
        operators = [c.operator for c in inner.conditions]
        values = [c.value for c in inner.conditions]

        assert DataSearchOperator.is_null in operators
        assert False in values  # is_null(False)
        assert False in values  # not_equals(False)
        assert 0 in values  # not_equals(0)
        assert "" in values  # not_equals("")
        assert [] in values  # not_equals([])

    def test_truthy_falsy_opposite(self):
        """Test that is_truthy and is_falsy are logical opposites."""
        # Find records that are truthy
        q1 = QB["status"].is_truthy()
        # Find records that are NOT falsy should be similar concept
        q2 = ~QB["status"].is_falsy()

        query1 = q1.build()
        query2 = q2.build()

        # Both should create complex conditions
        assert isinstance(query1.conditions[0], DataSearchGroup)
        assert isinstance(query2.conditions[0], DataSearchGroup)

    def test_boolean_methods_practical_example(self):
        """Test practical usage of boolean convenience methods."""
        # Find active, verified users who are not deleted
        q = QB["active"].is_true() & QB["verified"].is_true() & QB["deleted"].is_false()
        query = q.build()
        root = query.conditions[0]

        assert root.operator == DataSearchLogicOperator.and_op
        # Structure is nested due to & chaining: (a & b) & c
        # So root has 2 conditions: left group and right condition
        assert len(root.conditions) == 2

    def test_truthy_with_other_conditions(self):
        """Test is_truthy() combined with other query conditions."""
        q = QB["status"].is_truthy() & QB["age"].gte(18)
        query = q.build()
        root = query.conditions[0]

        assert root.operator == DataSearchLogicOperator.and_op
        assert len(root.conditions) == 2

    def test_is_truthy_rejects_empty_list(self):
        """Test that is_truthy() correctly rejects empty list."""
        q = QB["tags"].is_truthy()
        query = q.build()
        root = query.conditions[0]

        # Should check not equals []
        assert root.operator == DataSearchLogicOperator.and_op
        values = [c.value for c in root.conditions]
        assert [] in values

    def test_is_falsy_matches_empty_list(self):
        """Test that is_falsy() correctly matches empty list."""
        q = QB["tags"].is_falsy()
        query = q.build()
        root = query.conditions[0]

        # Should be NOT(is_truthy()), with inner AND group having [] in conditions
        assert root.operator == DataSearchLogicOperator.not_op
        inner = root.conditions[0]
        assert isinstance(inner, DataSearchGroup)
        assert inner.operator == DataSearchLogicOperator.and_op
        values = [c.value for c in inner.conditions]
        assert [] in values

    def test_invert_operator_is_falsy(self):
        """Test that ~field syntax produces is_falsy() condition."""
        q1 = ~QB["comment"]
        q2 = QB["comment"].is_falsy()

        query1 = q1.build()
        query2 = q2.build()

        # Both should produce identical conditions
        assert isinstance(query1.conditions[0], DataSearchGroup)
        assert isinstance(query2.conditions[0], DataSearchGroup)

        root1 = query1.conditions[0]
        root2 = query2.conditions[0]

        # Should be NOT groups
        assert root1.operator == DataSearchLogicOperator.not_op
        assert root2.operator == DataSearchLogicOperator.not_op

        # Should have 1 inner condition (the is_truthy AND group)
        assert len(root1.conditions) == 1
        assert len(root2.conditions) == 1

        # Check inner AND groups match
        inner1 = root1.conditions[0]
        inner2 = root2.conditions[0]

        assert isinstance(inner1, DataSearchGroup)
        assert isinstance(inner2, DataSearchGroup)
        assert inner1.operator == DataSearchLogicOperator.and_op
        assert inner2.operator == DataSearchLogicOperator.and_op
        assert len(inner1.conditions) == 5
        assert len(inner2.conditions) == 5

        # Check values match
        values1 = [c.value for c in inner1.conditions]
        values2 = [c.value for c in inner2.conditions]

        # Convert to comparable form (use tuple for lists)
        def normalize_value(v):
            return tuple(v) if isinstance(v, list) else v

        normalized1 = set(normalize_value(v) for v in values1)
        normalized2 = set(normalize_value(v) for v in values2)

        assert normalized1 == normalized2
        assert False in values1  # is_null(False)
        assert False in values1  # not_equals(False)
        assert 0 in values1  # not_equals(0)
        assert "" in values1  # not_equals("")
        assert [] in values1  # not_equals([])

    def test_invert_operator_combined_with_other_conditions(self):
        """Test ~field syntax in complex queries."""
        # Active tasks without comments
        q = (QB["status"] == "active") & ~QB["comment"]
        query = q.build()
        root = query.conditions[0]

        assert isinstance(root, DataSearchGroup)
        assert root.operator == DataSearchLogicOperator.and_op
        assert len(root.conditions) == 2

        # First condition: status == "active"
        assert root.conditions[0].field_path == "status"
        assert root.conditions[0].operator == DataSearchOperator.equals

        # Second condition: is_falsy() group (NOT with inner AND)
        falsy_group = root.conditions[1]
        assert isinstance(falsy_group, DataSearchGroup)
        assert falsy_group.operator == DataSearchLogicOperator.not_op
        assert len(falsy_group.conditions) == 1
        # Inner is_truthy AND group
        inner = falsy_group.conditions[0]
        assert isinstance(inner, DataSearchGroup)
        assert inner.operator == DataSearchLogicOperator.and_op
        assert len(inner.conditions) == 5

    def test_invert_operator_practical_examples(self):
        """Test practical use cases for ~ operator."""
        # Find items without tags
        q1 = ~QB["tags"]
        query1 = q1.build()
        assert isinstance(query1.conditions[0], DataSearchGroup)

        # Find items without descriptions (empty or null)
        q2 = ~QB["description"]
        query2 = q2.build()
        assert isinstance(query2.conditions[0], DataSearchGroup)

        # Find inactive items (status is falsy)
        q3 = ~QB["status"]
        query3 = q3.build()
        assert isinstance(query3.conditions[0], DataSearchGroup)

    def test_length_method(self):
        """Test length() method for querying field length."""
        from autocrud.types import FieldTransform

        # String length
        q = QB["name"].length() > 10
        query = q.build()
        cond = query.conditions[0]

        assert cond.field_path == "name"  # Field path unchanged
        assert cond.transform == FieldTransform.length  # Transform applied
        assert cond.operator == DataSearchOperator.greater_than
        assert cond.value == 10

    def test_length_with_different_operators(self):
        """Test length() with various comparison operators."""
        from autocrud.types import FieldTransform

        # Exact length
        q1 = QB["tags"].length() == 3
        cond1 = q1.build().conditions[0]
        assert cond1.field_path == "tags"
        assert cond1.transform == FieldTransform.length
        assert cond1.operator == DataSearchOperator.equals

        # Length range
        q2 = QB["description"].length().between(50, 200)
        query2 = q2.build()
        group = query2.conditions[0]
        assert isinstance(group, DataSearchGroup)
        assert group.operator == DataSearchLogicOperator.and_op
        assert group.conditions[0].field_path == "description"
        assert group.conditions[0].transform == FieldTransform.length
        assert group.conditions[1].field_path == "description"
        assert group.conditions[1].transform == FieldTransform.length

        # Less than
        q3 = QB["items"].length() < 5
        cond3 = q3.build().conditions[0]
        assert cond3.field_path == "items"
        assert cond3.transform == FieldTransform.length
        assert cond3.operator == DataSearchOperator.less_than

    def test_length_empty_check(self):
        """Test length() for checking empty collections."""
        from autocrud.types import FieldTransform

        # Empty list
        q1 = QB["tags"].length() == 0
        cond1 = q1.build().conditions[0]
        assert cond1.field_path == "tags"
        assert cond1.transform == FieldTransform.length
        assert cond1.value == 0

        # Non-empty
        q2 = QB["items"].length() > 0
        cond2 = q2.build().conditions[0]
        assert cond2.field_path == "items"
        assert cond2.transform == FieldTransform.length
        assert cond2.operator == DataSearchOperator.greater_than
        assert cond2.value == 0

    def test_length_combined_with_other_conditions(self):
        """Test combining length() with other query conditions."""
        from autocrud.types import FieldTransform

        q = (QB["tags"].length() >= 3) & (QB["status"] == "active")
        query = q.build()
        group = query.conditions[0]

        assert group.operator == DataSearchLogicOperator.and_op
        assert len(group.conditions) == 2
        assert group.conditions[0].field_path == "tags"
        assert group.conditions[0].transform == FieldTransform.length
        assert group.conditions[1].field_path == "status"
        assert group.conditions[1].transform is None  # No transform

    def test_length_on_nested_fields(self):
        """Test length() on nested field paths."""
        from autocrud.types import FieldTransform

        q = QB["user.tags"].length() > 5
        cond = q.build().conditions[0]

        assert cond.field_path == "user.tags"
        assert cond.transform == FieldTransform.length
        assert cond.operator == DataSearchOperator.greater_than
        assert cond.value == 5

    def test_length_with_resource_manager(self, resource_manager: ResourceManager):
        """Test length() integration with actual resource search."""
        # Search for resources where name length > 5
        query = QB["name"].length() > 5
        results = resource_manager.search_resources(query)

        # Charlie (7 chars) should match
        assert len(results) == 1
        assert results[0].indexed_data["name"] == "Charlie"

    def test_length_with_list_field(self, resource_manager: ResourceManager):
        """Test length() on list fields using a new indexed field."""
        import datetime as dt
        from zoneinfo import ZoneInfo

        # Add a resource with tags
        now = dt.datetime.now(ZoneInfo("UTC"))
        meta_with_tags = ResourceMeta(
            resource_id="5",
            current_revision_id="5:1",
            total_revision_count=1,
            created_time=now,
            updated_time=now,
            created_by="user5",
            updated_by="user5",
            indexed_data={
                "name": "Eve",
                "age": 28,
                "dept": "IT",
                "tags": ["python", "docker", "k8s"],
            },
        )
        resource_manager.storage._meta_store["5"] = meta_with_tags

        # Search for resources with more than 2 tags
        query = QB["tags"].length() > 2
        results = resource_manager.search_resources(query)

        assert len(results) == 1
        assert results[0].indexed_data["name"] == "Eve"
        assert len(results[0].indexed_data["tags"]) == 3

    def test_length_equals_zero(self, resource_manager: ResourceManager):
        """Test length() == 0 for empty collections."""
        import datetime as dt
        from zoneinfo import ZoneInfo

        # Add a resource with empty tags
        now = dt.datetime.now(ZoneInfo("UTC"))
        meta_empty = ResourceMeta(
            resource_id="6",
            current_revision_id="6:1",
            total_revision_count=1,
            created_time=now,
            updated_time=now,
            created_by="user6",
            updated_by="user6",
            indexed_data={"name": "Frank", "age": 45, "dept": "HR", "tags": []},
        )
        resource_manager.storage._meta_store["6"] = meta_empty

        # Search for resources with no tags
        query = QB["tags"].length() == 0
        results = resource_manager.search_resources(query)

        # Only Frank should match
        names = [r.indexed_data["name"] for r in results]
        assert "Frank" in names


class TestQueryBuilderEdgeCases:
    """Test edge cases and error conditions for Query Builder."""

    def test_all_empty_conditions_returns_no_filter(self):
        """Test QB.all() with no conditions returns query matching all resources."""
        from autocrud.query import QB

        q = QB.all()
        query = q.build()

        # Should have no conditions (UNSET)
        assert query.conditions is UNSET
        # Should still support chaining
        assert query.limit == 10  # default limit

    def test_all_empty_with_chaining(self):
        """Test QB.all() with no conditions supports method chaining."""
        from autocrud.query import QB

        q = QB.all().sort("-created_time").limit(20)
        query = q.build()

        # No conditions
        assert query.conditions is UNSET
        # Chaining works
        assert query.limit == 20
        assert len(query.sorts) == 1

    def test_all_empty_with_and_operator(self):
        """Test QB.all() with no conditions can be combined with & operator."""
        from autocrud.query import QB

        q = QB.all() & (QB["age"] > 18)
        query = q.build()

        # Should have just the age condition
        assert len(query.conditions) == 1
        cond = query.conditions[0]
        assert isinstance(cond, DataSearchCondition)
        assert cond.field_path == "age"
        assert cond.operator == DataSearchOperator.greater_than

    def test_any_empty_conditions_raises_error(self):
        """Test QB.any() with no conditions raises ValueError."""
        from autocrud.query import QB

        with pytest.raises(
            ValueError, match="any\\(\\) requires at least one condition"
        ):
            QB.any()

    def test_all_single_condition_unwraps(self):
        """Test QB.all() with single condition returns unwrapped condition."""
        from autocrud.query import QB

        q = QB.all(QB["age"] > 18)
        query = q.build()

        # Should be a single condition, not wrapped in a group
        assert len(query.conditions) == 1
        cond = query.conditions[0]
        assert isinstance(cond, DataSearchCondition)
        assert cond.field_path == "age"
        assert cond.operator == DataSearchOperator.greater_than

    def test_any_single_condition_unwraps(self):
        """Test QB.any() with single condition returns unwrapped condition."""
        from autocrud.query import QB

        q = QB.any(QB["status"] == "active")
        query = q.build()

        # Should be a single condition, not wrapped in a group
        assert len(query.conditions) == 1
        cond = query.conditions[0]
        assert isinstance(cond, DataSearchCondition)
        assert cond.field_path == "status"
        assert cond.operator == DataSearchOperator.equals
