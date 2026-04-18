# Query Builder

AutoCRUD includes a programmatic query system for searching indexed resource fields.

Use it when you want expressive filtering logic in Python instead of building raw metadata query objects by hand.

---

## When to use it

The query builder is useful for:

- filtering lists by field values
- combining multiple conditions with AND or OR
- building reusable search logic in services
- keeping search code readable in tests and admin workflows

---

## Basic idea

AutoCRUD search works on indexed metadata and indexed fields.

A typical flow looks like this:

```python
results = manager.search_resources(query)
```

The query object can be assembled either from low-level search structs or through the higher-level query builder helpers.

---

## Field comparisons

The system supports common operators such as:

- equals
- not equals
- greater than or greater than or equal
- less than or less than or equal
- contains
- starts with and ends with
- in-list and not-in-list
- null and existence checks
- regex

These map to the built-in search operators used by the metadata layer.

---

## Low-level example with search conditions

```python
from autocrud.types import (
    DataSearchCondition,
    DataSearchOperator,
    ResourceMetaSearchQuery,
)

query = ResourceMetaSearchQuery(
    conditions=[
        DataSearchCondition(
            field_path="status",
            operator=DataSearchOperator.equals,
            value="open",
        ),
        DataSearchCondition(
            field_path="priority",
            operator=DataSearchOperator.greater_than_or_equal,
            value=3,
        ),
    ],
    limit=20,
)

results = manager.search_resources(query)
```

---

## Sorting results

You can sort by metadata fields or indexed data fields.

```python
from autocrud.types import (
    ResourceDataSearchSort,
    ResourceMetaSearchQuery,
    ResourceMetaSortDirection,
)

query = ResourceMetaSearchQuery(
    sorts=[
        ResourceDataSearchSort(
            direction=ResourceMetaSortDirection.descending,
            field_path="priority",
        )
    ]
)
```

---

## Combining conditions

For more complex logic, use grouped search conditions so your queries can express nested boolean rules.

This is especially useful for filters such as:

- open issues assigned to Alice or Bob
- resources created this week and not deleted
- items matching either a tag filter or a text prefix

---

## Important limitation

Queries only work reliably on fields that are indexed or available in metadata.

If a field is not indexed, searching by that field may not behave as you expect on every backend.

---

## Good practices

- index fields that you plan to search frequently
- keep filters small and explicit at first
- use grouped conditions when OR logic is required
- sort on fields that are already indexed to keep queries efficient
- treat the query layer as part of your application design, not only an API convenience

---

## Related pages

- [Query system](/autocrud/concepts/query-system)
- [Search indexing](/autocrud/concepts/search-indexing)
- [Routes generation](/autocrud/howto/routes)
