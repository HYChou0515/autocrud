import datetime as dt
import enum
import uuid
from typing import Optional, Union

import msgspec
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from autocrud.crud.core import AutoCRUD
from autocrud.crud.route_templates.graphql import GraphQLRouteTemplate
from autocrud.types import (
    ResourceMeta,
    Resource,
    RevisionInfo,
    RevisionStatus,
)


class StatusEnum(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class ComplexModel(msgspec.Struct):
    name: str
    tags: list[str]
    scores: set[int]
    metadata: dict[str, str]
    optional_field: Optional[str]
    union_field: Union[str, int]
    status: StatusEnum
    created_at: dt.datetime
    date_field: dt.date
    tuple_field: tuple[int, int]


@pytest.fixture
def autocrud_complex():
    crud = AutoCRUD(model_naming="kebab")
    crud.add_route_template(GraphQLRouteTemplate())
    crud.add_model(ComplexModel, indexed_fields=["name"])
    return crud


@pytest.fixture
def client_complex(autocrud_complex):
    app = FastAPI()
    router = APIRouter()
    autocrud_complex.apply(router)
    app.include_router(router)
    return TestClient(app)


def test_complex_types_schema(client_complex):
    query = """
    {
        __type(name: "complex_modelResource") {
            fields {
                name
                type {
                    name
                    kind
                    ofType {
                        name
                        kind
                    }
                }
            }
        }
    }
    """
    response = client_complex.post("/graphql", json={"query": query})
    if response.status_code != 200:
        print(f"Response status: {response.status_code}")
        print(f"Response content: {response.content}")
    assert response.status_code == 200
    data = response.json()
    # Just verify it doesn't crash and returns fields
    fields = data["data"]["__type"]["fields"]
    field_names = [f["name"] for f in fields]
    assert "data" in field_names
    assert "info" in field_names
    assert "meta" in field_names


def test_filtering_and_sorting(autocrud_complex, client_complex):
    rm = autocrud_complex.get_resource_manager(ComplexModel)

    now = dt.datetime.now(dt.timezone.utc)

    with rm.meta_provide("user1", now):
        rm.create(
            ComplexModel(
                name="A",
                tags=["a"],
                scores={1},
                metadata={"k": "v"},
                optional_field="opt",
                union_field="u",
                status=StatusEnum.ACTIVE,
                created_at=now,
                date_field=now.date(),
                tuple_field=(1, 2),
            )
        )

    with rm.meta_provide("user2", now + dt.timedelta(hours=1)):
        rm.create(
            ComplexModel(
                name="B",
                tags=["b"],
                scores={2},
                metadata={"k": "v"},
                optional_field=None,
                union_field=1,
                status=StatusEnum.INACTIVE,
                created_at=now + dt.timedelta(hours=1),
                date_field=now.date(),
                tuple_field=(3, 4),
            )
        )

    # Test filtering by created_bys
    query_created_by = """
    query {
        complex_model_list(query: {createdBys: ["user1"]}) {
            data {
                name
            }
        }
    }
    """
    response = client_complex.post("/graphql", json={"query": query_created_by})
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]["complex_model_list"]) == 1
    assert data["data"]["complex_model_list"][0]["data"]["name"] == "A"

    # Test sorting
    query_sort = """
    query {
        complex_model_list(query: {sorts: [{type: data, fieldPath: "name", direction: descending}]}) {
            data {
                name
            }
        }
    }
    """
    response = client_complex.post("/graphql", json={"query": query_sort})
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]["complex_model_list"]) == 2
    assert data["data"]["complex_model_list"][0]["data"]["name"] == "B"
    assert data["data"]["complex_model_list"][1]["data"]["name"] == "A"

    # Test data conditions
    query_condition = """
    query {
        complex_model_list(query: {dataConditions: [{condition: {fieldPath: "name", operator: equals, value: "B"}}]}) {
            data {
                name
            }
        }
    }
    """
    response = client_complex.post("/graphql", json={"query": query_condition})
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]["complex_model_list"]) == 1
    assert data["data"]["complex_model_list"][0]["data"]["name"] == "B"


def test_get_single_resource(autocrud_complex, client_complex):
    rm = autocrud_complex.get_resource_manager(ComplexModel)
    now = dt.datetime.now(dt.timezone.utc)

    with rm.meta_provide("user1", now):
        info = rm.create(
            ComplexModel(
                name="Single",
                tags=[],
                scores=set(),
                metadata={},
                optional_field=None,
                union_field="u",
                status=StatusEnum.ACTIVE,
                created_at=now,
                date_field=now.date(),
                tuple_field=(0, 0),
            )
        )

    resource_id = info.resource_id

    query = f"""
    query {{
        complex_model(resourceId: "{resource_id}") {{
            data {{
                name
            }}
            info {{
                resourceId
            }}
            meta {{
                createdBy
            }}
        }}
    }}
    """
    response = client_complex.post("/graphql", json={"query": query})
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["complex_model"]["data"]["name"] == "Single"
    assert data["data"]["complex_model"]["info"]["resourceId"] == resource_id
    assert data["data"]["complex_model"]["meta"]["createdBy"] == "user1"


def test_partial_fetching(autocrud_complex, client_complex):
    rm = autocrud_complex.get_resource_manager(ComplexModel)
    now = dt.datetime.now(dt.timezone.utc)

    with rm.meta_provide("user1", now):
        rm.create(
            ComplexModel(
                name="Partial",
                tags=["p"],
                scores={1},
                metadata={},
                optional_field=None,
                union_field="u",
                status=StatusEnum.ACTIVE,
                created_at=now,
                date_field=now.date(),
                tuple_field=(0, 0),
            )
        )

    # Query only name (partial)
    query = """
    query {
        complex_model_list {
            data {
                name
            }
        }
    }
    """
    response = client_complex.post("/graphql", json={"query": query})
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["complex_model_list"][0]["data"]["name"] == "Partial"
    # We can't easily verify get_partial was called without mocking, but this exercises the code path.


def test_error_handling(autocrud_complex, client_complex):
    # Query non-existent resource
    query = """
    query {
        complex_model(resourceId: "non-existent") {
            data {
                name
            }
        }
    }
    """
    response = client_complex.post("/graphql", json={"query": query})
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["complex_model"] is None


def test_extended_filtering_and_sorting(autocrud_complex, client_complex):
    rm = autocrud_complex.get_resource_manager(ComplexModel)
    now = dt.datetime.now(dt.timezone.utc)

    with rm.meta_provide("user1", now):
        rm.create(
            ComplexModel(
                name="A",
                tags=[],
                scores=set(),
                metadata={},
                optional_field=None,
                union_field="u",
                status=StatusEnum.ACTIVE,
                created_at=now,
                date_field=now.date(),
                tuple_field=(0, 0),
            )
        )

    with rm.meta_provide("user2", now + dt.timedelta(hours=1)):
        rm.create(
            ComplexModel(
                name="B",
                tags=[],
                scores=set(),
                metadata={},
                optional_field=None,
                union_field="u",
                status=StatusEnum.ACTIVE,
                created_at=now,
                date_field=now.date(),
                tuple_field=(0, 0),
            )
        )

    # Test updated_bys
    query_updated_by = """
    query {
        complex_model_list(query: {updatedBys: ["user2"]}) {
            data { name }
        }
    }
    """
    response = client_complex.post("/graphql", json={"query": query_updated_by})
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]["complex_model_list"]) == 1
    assert data["data"]["complex_model_list"][0]["data"]["name"] == "B"

    # Test limit and offset
    query_limit = """
    query {
        complex_model_list(query: {limit: 1, offset: 0, sorts: [{type: meta, key: created_time, direction: ascending}]}) {
            data { name }
        }
    }
    """
    response = client_complex.post("/graphql", json={"query": query_limit})
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]["complex_model_list"]) == 1
    assert data["data"]["complex_model_list"][0]["data"]["name"] == "A"

    query_offset = """
    query {
        complex_model_list(query: {limit: 1, offset: 1, sorts: [{type: meta, key: created_time, direction: ascending}]}) {
            data { name }
        }
    }
    """
    response = client_complex.post("/graphql", json={"query": query_offset})
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]["complex_model_list"]) == 1
    assert data["data"]["complex_model_list"][0]["data"]["name"] == "B"

    # Test time range filters
    start_iso = now.isoformat()
    end_iso = (now + dt.timedelta(minutes=30)).isoformat()
    query_time = f"""
    query {{
        complex_model_list(query: {{createdTimeStart: "{start_iso}", createdTimeEnd: "{end_iso}"}}) {{
            data {{ name }}
        }}
    }}
    """
    response = client_complex.post("/graphql", json={"query": query_time})
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]["complex_model_list"]) == 1
    assert data["data"]["complex_model_list"][0]["data"]["name"] == "A"


def test_get_resource_revision(autocrud_complex, client_complex):
    rm = autocrud_complex.get_resource_manager(ComplexModel)
    now = dt.datetime.now(dt.timezone.utc)

    resource_id = None
    rev1_id = None
    rev2_id = None

    with rm.meta_provide("user1", now):
        info = rm.create(
            ComplexModel(
                name="Rev1",
                tags=[],
                scores=set(),
                metadata={},
                optional_field=None,
                union_field="u",
                status=StatusEnum.ACTIVE,
                created_at=now,
                date_field=now.date(),
                tuple_field=(0, 0),
            )
        )
        resource_id = info.resource_id
        rev1_id = info.revision_id

    with rm.meta_provide("user1", now + dt.timedelta(minutes=1)):
        info = rm.update(
            resource_id,
            ComplexModel(
                name="Rev2",
                tags=[],
                scores=set(),
                metadata={},
                optional_field=None,
                union_field="u",
                status=StatusEnum.ACTIVE,
                created_at=now,
                date_field=now.date(),
                tuple_field=(0, 0),
            ),
        )
        rev2_id = info.revision_id

    # Fetch specific revision
    query = f"""
    query {{
        complex_model(resourceId: "{resource_id}", revisionId: "{rev1_id}") {{
            data {{ name }}
        }}
    }}
    """
    response = client_complex.post("/graphql", json={"query": query})
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["complex_model"]["data"]["name"] == "Rev1"

    # Fetch current (Rev2)
    query_current = f"""
    query {{
        complex_model(resourceId: "{resource_id}") {{
            data {{ name }}
        }}
    }}
    """
    response = client_complex.post("/graphql", json={"query": query_current})
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["complex_model"]["data"]["name"] == "Rev2"


# --- Extended Coverage Tests ---


class ComplexUnionModel(msgspec.Struct):
    complex_field: Optional[Union[str, int]]


class DateModel(msgspec.Struct):
    d: dt.date


class SimpleStruct(msgspec.Struct):
    name: str


class DefaultFieldModel(msgspec.Struct):
    val: int = 42


class MockListResourceManager:
    resource_type = list[SimpleStruct]

    def meta_provide(self, user, now):
        from contextlib import contextmanager

        @contextmanager
        def cm():
            yield

        return cm()

    def get_meta(self, resource_id):
        return ResourceMeta(
            resource_id=resource_id,
            current_revision_id="rev1",
            created_time=dt.datetime.now(dt.timezone.utc),
            updated_time=dt.datetime.now(dt.timezone.utc),
            created_by="u",
            updated_by="u",
            total_revision_count=1,
            is_deleted=False,
        )

    def get_resource_revision(self, resource_id, revision_id):
        info = RevisionInfo(
            uid=uuid.uuid4(),
            resource_id=resource_id,
            revision_id=revision_id,
            created_time=dt.datetime.now(dt.timezone.utc),
            updated_time=dt.datetime.now(dt.timezone.utc),
            created_by="u",
            updated_by="u",
            status=RevisionStatus.stable,
        )
        return Resource(info=info, data=[SimpleStruct(name="full")])

    def get_partial(self, rid, rev, fields):
        return [SimpleStruct(name="partial")]

    def search_resources(self, query):
        return [
            ResourceMeta(
                resource_id="1",
                current_revision_id="rev1",
                created_time=dt.datetime.now(dt.timezone.utc),
                updated_time=dt.datetime.now(dt.timezone.utc),
                created_by="u",
                updated_by="u",
                total_revision_count=1,
                is_deleted=False,
            )
        ]

    def get_revision_info(self, rid, rev):
        return None


class MockDictResourceManager:
    resource_type = dict

    def meta_provide(self, *args):
        from contextlib import contextmanager

        @contextmanager
        def cm():
            yield

        return cm()

    def get_meta(self, resource_id):
        return ResourceMeta(
            resource_id=resource_id,
            current_revision_id="rev1",
            created_time=dt.datetime.now(dt.timezone.utc),
            updated_time=dt.datetime.now(dt.timezone.utc),
            created_by="u",
            updated_by="u",
            total_revision_count=1,
            is_deleted=False,
        )

    def get_resource_revision(self, resource_id, revision_id):
        info = RevisionInfo(
            uid=uuid.uuid4(),
            resource_id=resource_id,
            revision_id=revision_id,
            created_time=dt.datetime.now(dt.timezone.utc),
            updated_time=dt.datetime.now(dt.timezone.utc),
            created_by="u",
            updated_by="u",
            status=RevisionStatus.stable,
        )
        return Resource(info=info, data={"a": 1})

    def search_resources(self, query):
        return [
            ResourceMeta(
                resource_id="1",
                current_revision_id="rev1",
                created_time=dt.datetime.now(dt.timezone.utc),
                updated_time=dt.datetime.now(dt.timezone.utc),
                created_by="u",
                updated_by="u",
                total_revision_count=1,
                is_deleted=False,
            )
        ]

    def get_revision_info(self, rid, rev):
        return None


@pytest.fixture
def autocrud_extended():
    crud = AutoCRUD(model_naming="kebab")
    crud.add_route_template(GraphQLRouteTemplate())
    crud.add_model(ComplexUnionModel)
    crud.add_model(DateModel)
    crud.add_model(DefaultFieldModel)

    crud.resource_managers["list_model"] = MockListResourceManager()
    crud.resource_managers["dict_model"] = MockDictResourceManager()

    return crud


@pytest.fixture
def client_extended(autocrud_extended):
    app = FastAPI()
    router = APIRouter()
    autocrud_extended.apply(router)
    app.include_router(router)
    return TestClient(app)


def test_default_field_coverage(client_extended):
    query = "{ __schema { types { name } } }"
    response = client_extended.post("/graphql", json={"query": query})
    assert response.status_code == 200


def test_complex_union_coverage(client_extended):
    query = "{ __schema { types { name } } }"
    response = client_extended.post("/graphql", json={"query": query})
    assert response.status_code == 200


def test_date_coverage(autocrud_extended, client_extended):
    rm = autocrud_extended.get_resource_manager(DateModel)
    with rm.meta_provide("user", dt.datetime.now(dt.timezone.utc)):
        rm.create(DateModel(d=dt.date(2023, 1, 1)))

    query = """
    query {
        date_model_list {
            data { d }
        }
    }
    """
    response = client_extended.post("/graphql", json={"query": query})
    assert response.status_code == 200
    assert response.json()["data"]["date_model_list"][0]["data"]["d"] == "2023-01-01"


def test_list_filters(autocrud_extended, client_extended):
    query = """
    query {
        date_model_list(query: {
            isDeleted: false,
            createdTimeEnd: "2030-01-01T00:00:00Z"
        }) {
            data { d }
        }
    }
    """
    response = client_extended.post("/graphql", json={"query": query})
    assert response.status_code == 200


def test_list_resource_partial(client_extended):
    query_list = """
    query {
        list_model_list {
            data { name }
        }
    }
    """
    response = client_extended.post("/graphql", json={"query": query_list})
    assert response.status_code == 200
    assert response.json()["data"]["list_model_list"][0]["data"][0]["name"] == "partial"

    query_get = """
    query {
        list_model(resourceId: "1") {
            data { name }
        }
    }
    """
    response = client_extended.post("/graphql", json={"query": query_get})
    assert response.status_code == 200
    assert response.json()["data"]["list_model"]["data"][0]["name"] == "partial"


def test_fetch_info_only(autocrud_extended, client_extended):
    rm = autocrud_extended.get_resource_manager(DateModel)
    with rm.meta_provide("user", dt.datetime.now(dt.timezone.utc)):
        rm.create(DateModel(d=dt.date(2023, 1, 1)))

    query = """
    query {
        date_model_list {
            info { resourceId }
        }
    }
    """
    response = client_extended.post("/graphql", json={"query": query})
    assert response.status_code == 200
    assert "data" not in response.json()["data"]["date_model_list"][0]
    assert (
        response.json()["data"]["date_model_list"][0]["info"]["resourceId"] is not None
    )


def test_full_data_fetch_fallback(client_extended):
    query = """
    query {
        dict_model_list {
            data
        }
    }
    """
    response = client_extended.post("/graphql", json={"query": query})
    assert response.status_code == 200
    assert response.json()["data"]["dict_model_list"][0]["data"] == {"a": 1}
