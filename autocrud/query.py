from typing import Any, Self

from msgspec import UNSET

from autocrud.types import (
    DataSearchCondition,
    DataSearchFilter,
    DataSearchGroup,
    DataSearchLogicOperator,
    DataSearchOperator,
    FieldTransform,
    ResourceDataSearchSort,
    ResourceMetaSearchQuery,
    ResourceMetaSearchSort,
    ResourceMetaSortDirection,
    ResourceMetaSortKey,
)


class Query:
    """Builder for ResourceMetaSearchQuery."""

    def __init__(self, condition: DataSearchFilter | None = None):
        self._condition = condition
        self._limit: int = 10
        self._offset: int = 0
        self._sorts: list[ResourceMetaSearchSort | ResourceDataSearchSort] = []

    def limit(self, limit: int) -> Self:
        self._limit = limit
        return self

    def offset(self, offset: int) -> Self:
        self._offset = offset
        return self

    def sort(
        self, *sorts: ResourceMetaSearchSort | ResourceDataSearchSort | str
    ) -> Self:
        """Add sorting criteria.

        Args:
            *sorts: Sort objects or field name strings.
                   Strings can be prefixed with '+' (ascending) or '-' (descending).
                   If no prefix, defaults to ascending.

        Returns:
            Self for chaining

        Example:
            query.sort(QB.created_time().desc())
            query.sort("-created_time", "+name")  # created_time desc, name asc
            query.sort("age")  # age ascending (default)
        """
        for s in sorts:
            if isinstance(s, str):
                # Parse string format: "+field" or "-field" or "field"
                if s.startswith("-"):
                    field_name = s[1:]
                    direction = ResourceMetaSortDirection.descending
                elif s.startswith("+"):
                    field_name = s[1:]
                    direction = ResourceMetaSortDirection.ascending
                else:
                    field_name = s
                    direction = ResourceMetaSortDirection.ascending

                # Check if it's a meta field
                if field_name in ResourceMetaSortKey.__members__:
                    sort_obj = ResourceMetaSearchSort(
                        direction=direction, key=ResourceMetaSortKey(field_name)
                    )
                else:
                    sort_obj = ResourceDataSearchSort(
                        direction=direction, field_path=field_name
                    )
                self._sorts.append(sort_obj)
            else:
                self._sorts.append(s)
        return self

    def order_by(
        self, *sorts: ResourceMetaSearchSort | ResourceDataSearchSort | str
    ) -> Self:
        """Alias for sort(). Add sorting criteria.

        Args:
            *sorts: Sort objects or field name strings.
                   Strings can be prefixed with '+' (ascending) or '-' (descending).

        Returns:
            Self for chaining

        Example:
            query.order_by("-created_time", "+name")
            query.order_by(QB.age().desc())
        """
        return self.sort(*sorts)

    def page(self, page: int, size: int = 20) -> Self:
        """Set pagination parameters.

        Args:
            page: Page number (1-based, first page is 1)
            size: Number of items per page (default: 20)

        Returns:
            Self for chaining

        Example:
            QB.status.eq("active").page(1, 10)  # First page, 10 items
            QB.status.eq("active").page(2, 20)  # Second page, 20 items
            QB.status.eq("active").page(3)      # Third page, default 20 items
        """
        if page < 1:
            raise ValueError(f"Page number must be >= 1, got {page}")
        if size < 1:
            raise ValueError(f"Page size must be >= 1, got {size}")

        self._offset = (page - 1) * size
        self._limit = size
        return self

    def first(self) -> Self:
        """Set limit to 1 to retrieve only the first result.

        Returns:
            Self for chaining

        Example:
            QB.status.eq("active").sort(QB.created_time.desc()).first()
        """
        self._limit = 1
        return self

    def build(self) -> ResourceMetaSearchQuery:
        conditions = [self._condition] if self._condition else UNSET
        return ResourceMetaSearchQuery(
            conditions=conditions,
            limit=self._limit,
            offset=self._offset,
            sorts=self._sorts if self._sorts else UNSET,
        )


class ConditionBuilder(Query):
    """Wraps a DataSearchFilter and allows combining with other conditions."""

    def __init__(self, condition: DataSearchFilter | None):
        super().__init__(condition)

    def __and__(
        self, other: "ConditionBuilder | DataSearchFilter"
    ) -> "ConditionBuilder":
        if isinstance(other, Query):
            other_cond = other._condition
        else:
            other_cond = other

        # If strict type checking complains about None, we assume valid usage for now or handle None
        if self._condition is None:
            return ConditionBuilder(other_cond)
        if other_cond is None:
            return self

        return ConditionBuilder(
            DataSearchGroup(
                operator=DataSearchLogicOperator.and_op,
                conditions=[self._condition, other_cond],
            )
        )

    def __or__(
        self, other: "ConditionBuilder | DataSearchFilter"
    ) -> "ConditionBuilder":
        if isinstance(other, Query):
            other_cond = other._condition
        else:
            other_cond = other

        if self._condition is None:
            return ConditionBuilder(other_cond)
        if other_cond is None:
            return self

        return ConditionBuilder(
            DataSearchGroup(
                operator=DataSearchLogicOperator.or_op,
                conditions=[self._condition, other_cond],
            )
        )

    def __invert__(self) -> "ConditionBuilder":
        if self._condition is None:
            raise ValueError("Cannot negate an empty condition")
        return ConditionBuilder(
            DataSearchGroup(
                operator=DataSearchLogicOperator.not_op, conditions=[self._condition]
            )
        )

    def and_(self, other) -> "ConditionBuilder":
        return self & other

    def or_(self, other) -> "ConditionBuilder":
        return self | other

    def filter(self, *conditions: "ConditionBuilder") -> "ConditionBuilder":
        """Add AND conditions to the query. More readable than using &.

        Args:
            *conditions: Additional conditions to AND with current condition

        Returns:
            ConditionBuilder with combined conditions

        Example:
            QB["age"].gt(18).filter(QB["status"].eq("active"), QB["verified"].eq(True))
            # Equivalent to: (QB["age"] > 18) & (QB["status"] == "active") & (QB["verified"] == True)
        """
        result = self
        for cond in conditions:
            result = result & cond
        return result

    def exclude(self, *conditions: "ConditionBuilder") -> "ConditionBuilder":
        """Add NOT conditions to the query. More readable than using ~.

        Args:
            *conditions: Conditions to exclude (will be negated and ANDed)

        Returns:
            ConditionBuilder with excluded conditions

        Example:
            QB["status"].eq("active").exclude(QB["role"].eq("guest"), QB["deleted"].eq(True))
            # Equivalent to: (status == "active") & ~(role == "guest") & ~(deleted == True)
        """
        result = self
        for cond in conditions:
            result = result & (~cond)
        return result

    # Dunder methods for chained comparisons
    # These allow: 3 <= QB.field <= 5, QB.foo == QB.bar == 2
    def __eq__(self, value: Any) -> "ConditionBuilder":
        """Support chained comparison: condition == value.

        Example:
            QB.foo == QB.bar == 2  # Both foo and bar equal to 2
        """
        if not isinstance(self._condition, DataSearchCondition):
            raise TypeError(
                "Can only use comparison operators on single conditions, not logical groups"
            )
        return ConditionBuilder(
            DataSearchCondition(
                field_path=self._condition.field_path,
                operator=DataSearchOperator.equals,
                value=value,
            )
        )

    def __ne__(self, value: Any) -> "ConditionBuilder":
        """Support chained comparison: condition != value."""
        if not isinstance(self._condition, DataSearchCondition):
            raise TypeError(
                "Can only use comparison operators on single conditions, not logical groups"
            )
        return ConditionBuilder(
            DataSearchCondition(
                field_path=self._condition.field_path,
                operator=DataSearchOperator.not_equals,
                value=value,
            )
        )

    def __ge__(self, value: Any) -> "ConditionBuilder":
        """Support chained comparison: condition >= value (for right side of chain)."""
        if not isinstance(self._condition, DataSearchCondition):
            raise TypeError(
                "Can only use comparison operators on single conditions, not logical groups"
            )
        return ConditionBuilder(
            DataSearchCondition(
                field_path=self._condition.field_path,
                operator=DataSearchOperator.greater_than_or_equal,
                value=value,
            )
        )

    def __gt__(self, value: Any) -> "ConditionBuilder":
        """Support chained comparison: condition > value."""
        if not isinstance(self._condition, DataSearchCondition):
            raise TypeError(
                "Can only use comparison operators on single conditions, not logical groups"
            )
        return ConditionBuilder(
            DataSearchCondition(
                field_path=self._condition.field_path,
                operator=DataSearchOperator.greater_than,
                value=value,
            )
        )

    def __le__(self, value: Any) -> "ConditionBuilder":
        """Support chained comparison: condition <= value."""
        if not isinstance(self._condition, DataSearchCondition):
            raise TypeError(
                "Can only use comparison operators on single conditions, not logical groups"
            )
        return ConditionBuilder(
            DataSearchCondition(
                field_path=self._condition.field_path,
                operator=DataSearchOperator.less_than_or_equal,
                value=value,
            )
        )

    def __lt__(self, value: Any) -> "ConditionBuilder":
        """Support chained comparison: condition < value."""
        if not isinstance(self._condition, DataSearchCondition):
            raise TypeError(
                "Can only use comparison operators on single conditions, not logical groups"
            )
        return ConditionBuilder(
            DataSearchCondition(
                field_path=self._condition.field_path,
                operator=DataSearchOperator.less_than,
                value=value,
            )
        )


class Field(ConditionBuilder):
    def __init__(self, name: str, transform: FieldTransform | None = None):
        self.name = name
        self.transform = transform
        # Default behavior: Field acts as is_truthy() condition
        # This allows QB["foo"] to be used directly in logical operations
        super().__init__(self._create_truthy_condition())

    def _create_truthy_condition(self) -> DataSearchGroup:
        """Create truthy condition: not null, not false, not 0, not empty string, not empty list."""
        return DataSearchGroup(
            operator=DataSearchLogicOperator.and_op,
            conditions=[
                DataSearchCondition(
                    field_path=self.name,
                    operator=DataSearchOperator.is_null,
                    value=False,
                ),
                DataSearchCondition(
                    field_path=self.name,
                    operator=DataSearchOperator.not_equals,
                    value=False,
                ),
                DataSearchCondition(
                    field_path=self.name,
                    operator=DataSearchOperator.not_equals,
                    value=0,
                ),
                DataSearchCondition(
                    field_path=self.name,
                    operator=DataSearchOperator.not_equals,
                    value="",
                ),
                DataSearchCondition(
                    field_path=self.name,
                    operator=DataSearchOperator.not_equals,
                    value=[],
                ),
            ],
        )

    def _cond(
        self, op: DataSearchOperator, val: Any, transform: FieldTransform | None = None
    ) -> ConditionBuilder:
        return ConditionBuilder(
            DataSearchCondition(
                field_path=self.name,
                operator=op,
                value=val,
                transform=transform if transform is not None else self.transform,
            )
        )

    def eq(self, value: Any) -> ConditionBuilder:
        return self._cond(DataSearchOperator.equals, value)

    def ne(self, value: Any) -> ConditionBuilder:
        return self._cond(DataSearchOperator.not_equals, value)

    def gt(self, value: Any) -> ConditionBuilder:
        return self._cond(DataSearchOperator.greater_than, value)

    def gte(self, value: Any) -> ConditionBuilder:
        return self._cond(DataSearchOperator.greater_than_or_equal, value)

    def lt(self, value: Any) -> ConditionBuilder:
        return self._cond(DataSearchOperator.less_than, value)

    def lte(self, value: Any) -> ConditionBuilder:
        return self._cond(DataSearchOperator.less_than_or_equal, value)

    # Dunder methods for Pythonic syntax
    def __eq__(self, value: Any) -> ConditionBuilder:
        """Support field == value syntax."""
        return self.eq(value)

    def __ne__(self, value: Any) -> ConditionBuilder:
        """Support field != value syntax."""
        return self.ne(value)

    def __gt__(self, value: Any) -> ConditionBuilder:
        """Support field > value syntax."""
        return self.gt(value)

    def __ge__(self, value: Any) -> ConditionBuilder:
        """Support field >= value syntax."""
        return self.gte(value)

    def __lt__(self, value: Any) -> ConditionBuilder:
        """Support field < value syntax."""
        return self.lt(value)

    def __le__(self, value: Any) -> ConditionBuilder:
        """Support field <= value syntax."""
        return self.lte(value)

    def __mod__(self, value: str) -> ConditionBuilder:
        """Support field % pattern syntax for regex."""
        return self.regex(value)

    def __lshift__(self, value: list[Any]) -> ConditionBuilder:
        """Support field << [values] syntax for in_list."""
        return self.in_(value)

    def __rshift__(self, value: Any) -> ConditionBuilder:
        """Support field >> value syntax for contains."""
        return self.contains(value)

    def __invert__(self) -> ConditionBuilder:
        """Support ~field syntax for is_falsy().

        Override parent's NOT logic to directly return is_falsy() condition.
        This is more intuitive: ~field means "field is falsy", not "NOT (field is truthy)".

        Note: While logically equivalent, this returns the OR group directly
        instead of wrapping the truthy condition in a NOT group.

        Checks if field value is falsy (None, False, 0, "", []).

        Example:
            ~QB["comment"]  # Falsy values
            # Equivalent to: QB["comment"].is_falsy()
        """
        return self.is_falsy()

    def between(self, min_val: Any, max_val: Any) -> ConditionBuilder:
        """Support range query: field.between(min, max).

        Cleaner alternative to: (field >= min) & (field <= max)

        Args:
            min_val: Minimum value (inclusive)
            max_val: Maximum value (inclusive)

        Returns:
            ConditionBuilder with AND condition

        Example:
            QB["age"].between(18, 65)
            QB["price"].between(100, 500)
            QB.created_time().between(start_date, end_date)
        """
        return ConditionBuilder(
            DataSearchGroup(
                operator=DataSearchLogicOperator.and_op,
                conditions=[
                    DataSearchCondition(
                        field_path=self.name,
                        operator=DataSearchOperator.greater_than_or_equal,
                        value=min_val,
                        transform=self.transform,
                    ),
                    DataSearchCondition(
                        field_path=self.name,
                        operator=DataSearchOperator.less_than_or_equal,
                        value=max_val,
                        transform=self.transform,
                    ),
                ],
            )
        )

    def in_range(self, min_val: Any, max_val: Any) -> ConditionBuilder:
        """Alias for between(). Check if field value is within a range.

        Args:
            min_val: Minimum value (inclusive)
            max_val: Maximum value (inclusive)

        Returns:
            ConditionBuilder with range condition

        Example:
            QB["age"].in_range(18, 65)
            QB["price"].in_range(100, 500)
        """
        return self.between(min_val, max_val)

    def contains(self, value: Any) -> ConditionBuilder:
        return self._cond(DataSearchOperator.contains, value)

    def starts_with(self, value: Any) -> ConditionBuilder:
        return self._cond(DataSearchOperator.starts_with, value)

    def ends_with(self, value: Any) -> ConditionBuilder:
        return self._cond(DataSearchOperator.ends_with, value)

    def in_(self, value: list[Any]) -> ConditionBuilder:
        return self._cond(DataSearchOperator.in_list, value)

    def not_in(self, value: list[Any]) -> ConditionBuilder:
        return self._cond(DataSearchOperator.not_in_list, value)

    def is_null(self, value: bool = True) -> ConditionBuilder:
        return self._cond(DataSearchOperator.is_null, value)

    def is_not_null(self) -> ConditionBuilder:
        """Check if field is not null.

        Returns:
            ConditionBuilder with is_null(False) condition

        Example:
            QB["email"].is_not_null()
            QB["optional_field"].is_not_null()
        """
        return self._cond(DataSearchOperator.is_null, False)

    def has_value(self) -> ConditionBuilder:
        """Alias for is_not_null(). Check if field has a value (not null).

        Returns:
            ConditionBuilder with is_null(False) condition

        Example:
            QB["email"].has_value()
            QB["description"].has_value()
        """
        return self.is_not_null()

    def is_true(self) -> ConditionBuilder:
        """Check if field value is True.

        Returns:
            ConditionBuilder with equals(True) condition

        Example:
            QB["verified"].is_true()
            QB["active"].is_true()
        """
        return self.eq(True)

    def is_false(self) -> ConditionBuilder:
        """Check if field value is False.

        Returns:
            ConditionBuilder with equals(False) condition

        Example:
            QB["deleted"].is_false()
            QB["disabled"].is_false()
        """
        return self.eq(False)

    def is_truthy(self) -> ConditionBuilder:
        """Check if field has a truthy value (not null, not empty, not false, not 0).

        Returns:
            ConditionBuilder for: value != None AND value != False AND value != 0 AND value != "" AND value != []

        Example:
            QB["status"].is_truthy()  # Has meaningful value
            QB["count"].is_truthy()   # Not 0
            QB["tags"].is_truthy()    # Not empty list
        """
        return ConditionBuilder(self._create_truthy_condition())

    def is_falsy(self) -> ConditionBuilder:
        """Check if field has a falsy value (null, empty, false, or 0).

        Returns:
            ConditionBuilder for NOT(is_truthy): negation of truthy condition

        Example:
            QB["optional_field"].is_falsy()  # Empty or unset
            QB["count"].is_falsy()           # Zero or null
            QB["tags"].is_falsy()            # Empty list or null
        """
        # Falsy is the logical negation of truthy
        return ConditionBuilder(
            DataSearchGroup(
                operator=DataSearchLogicOperator.not_op,
                conditions=[self._create_truthy_condition()],
            )
        )

    def exists(self, value: bool = True) -> ConditionBuilder:
        return self._cond(DataSearchOperator.exists, value)

    def isna(self, value: bool = True) -> ConditionBuilder:
        return self._cond(DataSearchOperator.isna, value)

    def regex(self, value: str) -> ConditionBuilder:
        return self._cond(DataSearchOperator.regex, value)

    def match(self, value: str) -> ConditionBuilder:
        r"""Alias for regex(). Match field value against a regular expression pattern.

        Args:
            value: Regular expression pattern

        Returns:
            ConditionBuilder

        Example:
            QB["email"].match(r".*@gmail\.com$")
            QB["code"].match(r"^[A-Z]{3}-\d{4}$")
        """
        return self.regex(value)

    # Aliases and convenience methods
    def one_of(self, value: list[Any]) -> ConditionBuilder:
        """Alias for in_() with more Pythonic naming.

        Args:
            value: List of values to check against

        Returns:
            ConditionBuilder

        Example:
            QB.status.one_of(["active", "pending", "approved"])
        """
        return self.in_(value)

    def icontains(self, value: str) -> ConditionBuilder:
        """Case-insensitive contains using regex.

        Args:
            value: String to search for (case-insensitive)

        Returns:
            ConditionBuilder with regex condition

        Example:
            QB.name.icontains("alice")  # matches "Alice", "ALICE", "alice"
        """
        import re

        escaped = re.escape(value)
        return self.regex(f"(?i){escaped}")

    def istarts_with(self, value: str) -> ConditionBuilder:
        """Case-insensitive starts_with using regex.

        Args:
            value: Prefix to search for (case-insensitive)

        Returns:
            ConditionBuilder with regex condition

        Example:
            QB.email.istarts_with("admin")  # matches "Admin@", "ADMIN@", "admin@"
        """
        import re

        escaped = re.escape(value)
        return self.regex(f"(?i)^{escaped}")

    def iends_with(self, value: str) -> ConditionBuilder:
        """Case-insensitive ends_with using regex.

        Args:
            value: Suffix to search for (case-insensitive)

        Returns:
            ConditionBuilder with regex condition

        Example:
            QB.email.iends_with("@gmail.com")  # matches "@Gmail.com", "@GMAIL.COM"
        """
        import re

        escaped = re.escape(value)
        return self.regex(f"(?i){escaped}$")

    def not_contains(self, value: Any) -> ConditionBuilder:
        """Negation of contains - field does not contain value.

        Args:
            value: Value that should not be contained

        Returns:
            ConditionBuilder with NOT(contains) condition

        Example:
            QB.description.not_contains("spam")
        """
        return ~self.contains(value)

    def not_starts_with(self, value: Any) -> ConditionBuilder:
        """Negation of starts_with - field does not start with value.

        Args:
            value: Prefix that should not match

        Returns:
            ConditionBuilder with NOT(starts_with) condition

        Example:
            QB.email.not_starts_with("spam")
        """
        return ~self.starts_with(value)

    def not_ends_with(self, value: Any) -> ConditionBuilder:
        """Negation of ends_with - field does not end with value.

        Args:
            value: Suffix that should not match

        Returns:
            ConditionBuilder with NOT(ends_with) condition

        Example:
            QB.filename.not_ends_with(".tmp")
        """
        return ~self.ends_with(value)

    def is_empty(self) -> ConditionBuilder:
        """Check if field is empty string or null.

        Returns:
            ConditionBuilder with OR condition (empty string or null)

        Example:
            QB.description.is_empty()  # matches "" or null
        """
        return ConditionBuilder(
            DataSearchGroup(
                operator=DataSearchLogicOperator.or_op,
                conditions=[
                    DataSearchCondition(
                        field_path=self.name,
                        operator=DataSearchOperator.equals,
                        value="",
                    ),
                    DataSearchCondition(
                        field_path=self.name,
                        operator=DataSearchOperator.is_null,
                        value=True,
                    ),
                ],
            )
        )

    def is_blank(self) -> ConditionBuilder:
        """Check if field is empty, null, or contains only whitespace.

        Returns:
            ConditionBuilder with OR condition

        Example:
            QB.name.is_blank()  # matches "", null, "  ", "\\t\\n"
        """
        return ConditionBuilder(
            DataSearchGroup(
                operator=DataSearchLogicOperator.or_op,
                conditions=[
                    DataSearchCondition(
                        field_path=self.name,
                        operator=DataSearchOperator.equals,
                        value="",
                    ),
                    DataSearchCondition(
                        field_path=self.name,
                        operator=DataSearchOperator.is_null,
                        value=True,
                    ),
                    DataSearchCondition(
                        field_path=self.name,
                        operator=DataSearchOperator.regex,
                        value=r"^\s*$",
                    ),
                ],
            )
        )

    def like(self, pattern: str) -> ConditionBuilder:
        """SQL LIKE pattern matching with % and _ wildcards.

        Converts SQL LIKE patterns to appropriate operators:
        - %pattern% -> contains (if no _ inside)
        - pattern% -> starts_with (if no _ inside)
        - %pattern -> ends_with (if no _ inside)
        - Other patterns with % or _ -> regex

        Args:
            pattern: SQL LIKE pattern with % (any chars) and _ (single char)

        Returns:
            ConditionBuilder with appropriate condition

        Example:
            QB.name.like("Alice%")      # starts with "Alice"
            QB.email.like("%@gmail.com") # ends with "@gmail.com"
            QB.desc.like("%urgent%")    # contains "urgent"
            QB.code.like("A_C")         # matches "ABC", "A1C", etc. (regex)
        """
        import re

        # %pattern%
        if pattern.startswith("%") and pattern.endswith("%") and len(pattern) > 2:
            inner = pattern[1:-1]
            if "_" not in inner:
                return self.contains(inner)

        # pattern%
        if pattern.endswith("%") and not pattern.startswith("%"):
            prefix = pattern[:-1]
            if "_" not in prefix:
                return self.starts_with(prefix)

        # %pattern
        if pattern.startswith("%") and not pattern.endswith("%"):
            suffix = pattern[1:]
            if "_" not in suffix:
                return self.ends_with(suffix)

        # Convert SQL LIKE to regex
        # Strategy: manually replace % and _, then escape the rest
        # Step 1: Replace % with placeholder \x00 and _ with \x01
        temp = pattern.replace("%", "\x00").replace("_", "\x01")
        # Step 2: Escape all regex special chars
        regex_pattern = re.escape(temp)
        # Step 3: Convert placeholders to regex: \x00 -> .*, \x01 -> .
        regex_pattern = regex_pattern.replace("\x00", ".*").replace("\x01", ".")
        # Step 4: Add anchors for exact match
        regex_pattern = f"^{regex_pattern}$"

        return self.regex(regex_pattern)

    # Date/Time convenience methods
    def _parse_timezone(self, tz: Any) -> Any:
        """Parse timezone parameter to tzinfo object.

        Args:
            tz: Can be:
                - None: returns None (use local timezone)
                - int: UTC offset in hours (e.g., 8 for UTC+8, -4 for UTC-4)
                - str: UTC offset as string (e.g., "+8", "-4")
                - tzinfo: passed through as-is

        Returns:
            tzinfo object or None

        Example:
            _parse_timezone(None) -> None
            _parse_timezone(8) -> timezone(timedelta(hours=8))
            _parse_timezone("+8") -> timezone(timedelta(hours=8))
            _parse_timezone("-4") -> timezone(timedelta(hours=-4))
            _parse_timezone(ZoneInfo("UTC")) -> ZoneInfo("UTC")
        """
        if tz is None:
            return None

        # If already a tzinfo object, return as-is
        import datetime as dt

        if isinstance(tz, dt.tzinfo):
            return tz

        # Parse int or str offset
        if isinstance(tz, (int, str)):
            try:
                offset_hours = int(tz)
                return dt.timezone(dt.timedelta(hours=offset_hours))
            except (ValueError, TypeError):
                raise ValueError(
                    f"Invalid timezone offset: {tz}. Expected int or string like '+8' or '-4'"
                )

        raise TypeError(
            f"Invalid timezone type: {type(tz)}. Expected None, int, str, or tzinfo"
        )

    def today(self, tz: Any = None) -> ConditionBuilder:
        """Match values within today (00:00:00 to 23:59:59.999999).

        Args:
            tz: Timezone. Can be:
                - None: uses local timezone
                - int/str: UTC offset in hours (e.g., 8 or "+8" for UTC+8)
                - tzinfo: timezone object (e.g., ZoneInfo("UTC"))

        Returns:
            ConditionBuilder with between condition for today's date range

        Example:
            QB.created_time.today()  # Today in local timezone
            QB.created_time.today(8)  # Today in UTC+8
            QB.created_time.today("+8")  # Today in UTC+8
            QB.created_time.today("-4")  # Today in UTC-4
            QB.created_time.today(ZoneInfo("UTC"))  # Today in UTC
            QB.created_time.today(ZoneInfo("Asia/Taipei"))  # Today in Taipei
        """
        import datetime as dt

        tz = self._parse_timezone(tz)

        if tz is None:
            # Use local timezone
            now = dt.datetime.now().astimezone()
        else:
            now = dt.datetime.now(tz)

        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        return self.between(start_of_day, end_of_day)

    def this_week(self, tz: Any = None, week_start: int = 0) -> ConditionBuilder:
        """Match values within this week.

        Args:
            tz: Timezone. Can be:
                - None: uses local timezone
                - int/str: UTC offset in hours (e.g., 8 or "+8" for UTC+8)
                - tzinfo: timezone object (e.g., ZoneInfo("UTC"))
            week_start: Day of week to start (0=Monday, 6=Sunday). Default is 0 (Monday).

        Returns:
            ConditionBuilder with between condition for this week's date range

        Example:
            QB.created_time.this_week()  # This week (Mon-Sun) in local timezone
            QB.created_time.this_week(week_start=6)  # This week (Sun-Sat)
            QB.created_time.this_week(8)  # This week in UTC+8
            QB.created_time.this_week("+8")  # This week in UTC+8
            QB.created_time.this_week(ZoneInfo("UTC"))  # This week in UTC
        """
        import datetime as dt

        tz = self._parse_timezone(tz)

        if tz is None:
            now = dt.datetime.now().astimezone()
        else:
            now = dt.datetime.now(tz)

        # Calculate days since week_start
        current_weekday = now.weekday()  # 0=Monday, 6=Sunday
        days_since_start = (current_weekday - week_start) % 7

        # Start of week (at 00:00:00)
        start_of_week = (now - dt.timedelta(days=days_since_start)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        # End of week (at 23:59:59.999999)
        end_of_week = (start_of_week + dt.timedelta(days=6)).replace(
            hour=23, minute=59, second=59, microsecond=999999
        )

        return self.between(start_of_week, end_of_week)

    def last_n_days(self, n: int, tz: Any = None) -> ConditionBuilder:
        """Match values from the last N days (inclusive of today).

        Args:
            n: Number of days to look back (including today)
            tz: Timezone. Can be:
                - None: uses local timezone
                - int/str: UTC offset in hours (e.g., 8 or "+8" for UTC+8)
                - tzinfo: timezone object (e.g., ZoneInfo("UTC"))

        Returns:
            ConditionBuilder with gte condition for N days ago

        Example:
            QB.created_time().last_n_days(7)  # Last 7 days in local timezone
            QB.created_time().last_n_days(30, 8)  # Last 30 days in UTC+8
            QB.created_time().last_n_days(30, "+8")  # Last 30 days in UTC+8
            QB.created_time().last_n_days(30, ZoneInfo("UTC"))  # Last 30 days in UTC
        """
        import datetime as dt

        tz = self._parse_timezone(tz)

        if tz is None:
            now = dt.datetime.now().astimezone()
        else:
            now = dt.datetime.now(tz)

        # N days ago at 00:00:00
        n_days_ago = (now - dt.timedelta(days=n - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        return self.gte(n_days_ago)

    def yesterday(self, tz: Any = None) -> ConditionBuilder:
        """Match values from yesterday (00:00:00 to 23:59:59.999999).

        Args:
            tz: Timezone parameter (None, int, str, or tzinfo)

        Returns:
            ConditionBuilder with between condition for yesterday's date range

        Example:
            QB.created_time().yesterday()
            QB.created_time().yesterday(8)  # Yesterday in UTC+8
        """
        import datetime as dt

        tz = self._parse_timezone(tz)

        if tz is None:
            now = dt.datetime.now().astimezone()
        else:
            now = dt.datetime.now(tz)

        yesterday = now - dt.timedelta(days=1)
        start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)

        return self.between(start, end)

    def this_month(self, tz: Any = None) -> ConditionBuilder:
        """Match values within this month (1st to last day).

        Args:
            tz: Timezone parameter (None, int, str, or tzinfo)

        Returns:
            ConditionBuilder with between condition for this month's date range

        Example:
            QB.created_time().this_month()
            QB.created_time().this_month("+8")
        """
        import datetime as dt

        tz = self._parse_timezone(tz)

        if tz is None:
            now = dt.datetime.now().astimezone()
        else:
            now = dt.datetime.now(tz)

        # First day of month at 00:00:00
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Last day of month at 23:59:59.999999
        if now.month == 12:
            next_month = now.replace(year=now.year + 1, month=1, day=1)
        else:
            next_month = now.replace(month=now.month + 1, day=1)
        end_of_month = next_month - dt.timedelta(microseconds=1)

        return self.between(start_of_month, end_of_month)

    def this_year(self, tz: Any = None) -> ConditionBuilder:
        """Match values within this year (Jan 1 to Dec 31).

        Args:
            tz: Timezone parameter (None, int, str, or tzinfo)

        Returns:
            ConditionBuilder with between condition for this year's date range

        Example:
            QB.created_time().this_year()
            QB.created_time().this_year(ZoneInfo("UTC"))
        """
        import datetime as dt

        tz = self._parse_timezone(tz)

        if tz is None:
            now = dt.datetime.now().astimezone()
        else:
            now = dt.datetime.now(tz)

        # Jan 1 at 00:00:00
        start_of_year = now.replace(
            month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )

        # Dec 31 at 23:59:59.999999
        end_of_year = now.replace(
            month=12, day=31, hour=23, minute=59, second=59, microsecond=999999
        )

        return self.between(start_of_year, end_of_year)

    # Field transformation methods
    def length(self) -> "Field":
        """Get a virtual field representing the length of this field's value.

        This creates a field reference that can be used to query the length of:
        - Strings: character count
        - Lists/Arrays: number of elements
        - Dicts/Objects: number of keys

        Returns:
            Field instance with length transform applied

        Example:
            QB["tags"].length() > 3           # More than 3 tags
            QB["name"].length().between(5, 20) # Name length 5-20 chars
            QB["items"].length() == 0          # Empty list
            QB["description"].length() >= 100  # At least 100 characters

        Note:
            The actual length calculation is performed by the storage backend
            when executing the query using the FieldTransform.length transform.
            The returned Field also acts as is_truthy() by default.
        """
        return Field(self.name, transform=FieldTransform.length)

    # Sorting
    def asc(self) -> ResourceDataSearchSort | ResourceMetaSearchSort:
        if self.name in ResourceMetaSortKey.__members__:
            return ResourceMetaSearchSort(
                direction=ResourceMetaSortDirection.ascending,
                key=ResourceMetaSortKey(self.name),
            )
        return ResourceDataSearchSort(
            direction=ResourceMetaSortDirection.ascending, field_path=self.name
        )

    def desc(self) -> ResourceDataSearchSort | ResourceMetaSearchSort:
        if self.name in ResourceMetaSortKey.__members__:
            return ResourceMetaSearchSort(
                direction=ResourceMetaSortDirection.descending,
                key=ResourceMetaSortKey(self.name),
            )
        return ResourceDataSearchSort(
            direction=ResourceMetaSortDirection.descending, field_path=self.name
        )


class QueryBuilderMeta(type):
    def __getitem__(cls, name: str) -> Field:
        """Access data fields using bracket notation.

        Args:
            name: The field name (supports nested paths with dots)

        Returns:
            Field instance

        Example:
            QB["name"]  # Data field "name"
            QB["user.email"]  # Nested data field "user.email"
            QB["class"]  # Field name with reserved keyword
            QB["field-name"]  # Field name with special characters
        """
        return Field(name)


class QB(metaclass=QueryBuilderMeta):
    # Meta Attributes - Resource metadata fields with type hints and IDE support
    @staticmethod
    def resource_id() -> Field:
        """Resource unique identifier.

        Returns:
            Field for resource_id

        Example:
            QB.resource_id().eq("abc-123")
            QB.resource_id() << ["id1", "id2", "id3"]
        """
        return Field("resource_id")

    @staticmethod
    def revision_id() -> Field:
        """Current revision identifier.

        Returns:
            Field for current_revision_id

        Example:
            QB.revision_id().eq("rev-456")
        """
        return Field("current_revision_id")

    @staticmethod
    def created_time() -> Field:
        """Resource creation timestamp.

        Returns:
            Field for created_time

        Example:
            QB.created_time() >= datetime(2024, 1, 1)
            QB.created_time().today()
            QB.created_time().last_n_days(7)
        """
        return Field("created_time")

    @staticmethod
    def updated_time() -> Field:
        """Resource last update timestamp.

        Returns:
            Field for updated_time

        Example:
            QB.updated_time().this_week()
            QB.updated_time() >= datetime(2024, 1, 1)
        """
        return Field("updated_time")

    @staticmethod
    def created_by() -> Field:
        """User who created the resource.

        Returns:
            Field for created_by

        Example:
            QB.created_by().eq("admin")
            QB.created_by() << ["user1", "user2"]
        """
        return Field("created_by")

    @staticmethod
    def updated_by() -> Field:
        """User who last updated the resource.

        Returns:
            Field for updated_by

        Example:
            QB.updated_by().eq("system")
            QB.updated_by().ne("guest")
        """
        return Field("updated_by")

    @staticmethod
    def is_deleted() -> Field:
        """Resource deletion status.

        Returns:
            Field for is_deleted

        Example:
            QB.is_deleted().eq(False)
            QB.is_deleted() == False
        """
        return Field("is_deleted")

    @staticmethod
    def schema_version() -> Field:
        """Resource schema version.

        Returns:
            Field for schema_version

        Example:
            QB.schema_version().eq("v2")
        """
        return Field("schema_version")

    @staticmethod
    def total_revision_count() -> Field:
        """Total number of revisions for the resource.

        Returns:
            Field for total_revision_count

        Example:
            QB.total_revision_count() > 5
        """
        return Field("total_revision_count")

    # Combinators
    @staticmethod
    def all(*conditions: ConditionBuilder) -> ConditionBuilder:
        """Combine multiple conditions with AND logic.

        Args:
            *conditions: Variable number of ConditionBuilder instances.
                        If empty, returns a query with no conditions (matches all resources).

        Returns:
            ConditionBuilder with AND group, or no conditions if empty

        Example:
            QB.all(QB["age"] > 18, QB["status"] == "active", QB["score"] >= 80)
            # Equivalent to: (QB["age"] > 18) & (QB["status"] == "active") & (QB["score"] >= 80)

            QB.all()  # No conditions - matches all resources
        """
        if not conditions:
            # No conditions - return empty query (matches all)
            return ConditionBuilder(None)
        if len(conditions) == 1:
            return conditions[0]

        return ConditionBuilder(
            DataSearchGroup(
                operator=DataSearchLogicOperator.and_op,
                conditions=[c._condition for c in conditions],
            )
        )

    @staticmethod
    def any(*conditions: ConditionBuilder) -> ConditionBuilder:
        """Combine multiple conditions with OR logic.

        Args:
            *conditions: Variable number of ConditionBuilder instances

        Returns:
            ConditionBuilder with OR group

        Example:
            any(QB.status == "draft", QB.status == "pending", QB.status == "review")
            # Equivalent to: (QB.status == "draft") | (QB.status == "pending") | (QB.status == "review")
        """
        if not conditions:
            raise ValueError("any() requires at least one condition")
        if len(conditions) == 1:
            return conditions[0]

        return ConditionBuilder(
            DataSearchGroup(
                operator=DataSearchLogicOperator.or_op,
                conditions=[c._condition for c in conditions],
            )
        )
