# GraphQL

SpecStar can expose a GraphQL query endpoint in addition to the REST API.

This is useful when frontend or integration code wants more control over field selection and nested response shapes.

---

## Requirements

Install the GraphQL extra first:

```bash
pip install 'specstar[graphql]'
```

---

## Enable the GraphQL route

Add the GraphQL route template before applying SpecStar to your FastAPI app.

```python
from fastapi import FastAPI
from msgspec import Struct

from specstar import crud
from specstar.crud.route_templates.graphql import GraphQLRouteTemplate


class Character(Struct):
    name: str
    level: int = 1


app = FastAPI()

crud.add_model(Character)
crud.add_route_template(GraphQLRouteTemplate())
crud.apply(app)
```

After startup, GraphQL is mounted at:

- `/graphql`

---

## Query naming

The GraphQL route creates query fields based on the registered resource name.

For a resource named `character`, the common query fields are:

- `character` for a single resource by ID
- `character_list` for searching and listing resources

If your resource name contains hyphens, SpecStar normalizes it for GraphQL by using underscores.

---

## Example: fetch one resource

```graphql
query GetCharacter {
  character(resourceId: "character:demo-id") {
    meta {
      resourceId
      updatedTime
    }
    info {
      revisionId
      status
    }
    data {
      name
      level
    }
  }
}
```

---

## Example: list resources with filters

```graphql
query ListCharacters {
  characterList(
    query: {
      limit: 20
      dataConditions: [
        {
          condition: {
            fieldPath: "level"
            operator: greater_than_or_equal
            value: 10
          }
        }
      ]
    }
  ) {
    meta {
      resourceId
    }
    data {
      name
      level
    }
  }
}
```

This lets clients request only the sections and fields they actually need.

---

## Search and sorting support

The GraphQL list query supports the same ideas as the normal search API:

- deletion visibility
- created or updated time filters
- indexed field conditions
- pagination with limit and offset
- sorting by metadata or indexed fields

Use GraphQL when your client benefits from selective response shapes, but keep using REST when simple resource endpoints are enough.

---

## Good practices

- enable GraphQL only when your team actually needs it
- index fields that you expect to filter on frequently
- keep resource naming predictable so GraphQL field names stay easy to understand
- use REST for straightforward CRUD flows and GraphQL for query-heavy UI needs

---

## Related pages

- [Routes generation](/specstar/howto/routes)
- [Query builder](/specstar/howto/query-builder)
- [Examples](/specstar/examples/)
