import datetime as dt
import enum
import inspect
from typing import Any, Generic, Optional, TypeVar, get_args, get_origin

import msgspec
import strawberry
from fastapi import APIRouter, Depends
from strawberry.fastapi import GraphQLRouter
from strawberry.scalars import JSON
from strawberry.types import Info

from autocrud.crud.route_templates.basic import BaseRouteTemplate
from autocrud.types import (
    DataSearchCondition,
    DataSearchOperator,
    IResourceManager,
    ResourceMetaSearchQuery,
    ResourceMetaSearchSort,
    ResourceMetaSortDirection,
    ResourceMetaSortKey,
    ResourceDataSearchSort,
)

T = TypeVar("T")


@strawberry.enum
class GraphQLDataSearchOperator(str, enum.Enum):
    equals = "eq"
    not_equals = "ne"
    greater_than = "gt"
    greater_than_or_equal = "gte"
    less_than = "lt"
    less_than_or_equal = "lte"
    contains = "contains"
    starts_with = "starts_with"
    ends_with = "ends_with"
    in_list = "in"
    not_in_list = "not_in"


@strawberry.input
class DataSearchConditionInput:
    field_path: str
    operator: GraphQLDataSearchOperator
    value: JSON


@strawberry.enum
class GraphQLSortDirection(str, enum.Enum):
    ascending = "+"
    descending = "-"


@strawberry.enum
class GraphQLMetaSortKey(str, enum.Enum):
    created_time = "created_time"
    updated_time = "updated_time"
    resource_id = "resource_id"


@strawberry.enum
class GraphQLSortType(str, enum.Enum):
    data = "data"
    meta = "meta"


@strawberry.input
class SortInput:
    type: GraphQLSortType
    direction: GraphQLSortDirection = GraphQLSortDirection.ascending
    field_path: Optional[str] = None
    key: Optional[GraphQLMetaSortKey] = None


@strawberry.input
class SearchQueryInput:
    is_deleted: Optional[bool] = None
    created_time_start: Optional[dt.datetime] = None
    created_time_end: Optional[dt.datetime] = None
    updated_time_start: Optional[dt.datetime] = None
    updated_time_end: Optional[dt.datetime] = None
    created_bys: Optional[list[str]] = None
    updated_bys: Optional[list[str]] = None
    data_conditions: Optional[list[DataSearchConditionInput]] = None
    limit: int = 10
    offset: int = 0
    sorts: Optional[list[SortInput]] = None


@strawberry.type
class GraphQLRevisionInfo:
    uid: str
    resource_id: str
    revision_id: str
    parent_revision_id: Optional[str]
    parent_schema_version: Optional[str]
    schema_version: Optional[str]
    data_hash: Optional[str]
    status: str
    created_time: dt.datetime
    updated_time: dt.datetime
    created_by: str
    updated_by: str


@strawberry.type
class GraphQLResourceMeta:
    current_revision_id: str
    resource_id: str
    schema_version: Optional[str]
    total_revision_count: int
    created_time: dt.datetime
    updated_time: dt.datetime
    created_by: str
    updated_by: str
    is_deleted: bool
    indexed_data: Optional[JSON]


def _convert_msgspec_to_strawberry(type_: Any, name_prefix: str = "") -> Any:
    """Convert msgspec/python types to strawberry types recursively"""
    origin = get_origin(type_)
    args = get_args(type_)

    if type_ is Any or type_ is msgspec.UnsetType:
        return JSON

    if origin is list or origin is list:
        inner = _convert_msgspec_to_strawberry(args[0], name_prefix)
        return list[inner]

    if origin is dict:
        # GraphQL doesn't support arbitrary dicts well, use JSON
        return JSON

    if origin is set:
        inner = _convert_msgspec_to_strawberry(args[0], name_prefix)
        return list[inner]

    if origin is tuple:
        # Handle tuple as list for now or JSON
        return JSON

    if origin is type(None) or type_ is type(None):
        return Optional[JSON]  # Should not happen directly usually

    # Handle Optional (Union[T, None])
    if origin is not None and type(None) in args:
        non_none_args = [arg for arg in args if arg is not type(None)]
        if len(non_none_args) == 1:
            inner = _convert_msgspec_to_strawberry(non_none_args[0], name_prefix)
            return Optional[inner]
        else:
            return JSON  # Complex union

    if inspect.isclass(type_):
        if issubclass(type_, (str, int, float, bool)):
            return type_
        if issubclass(type_, dt.datetime):
            return dt.datetime
        if issubclass(type_, dt.date):
            return dt.date
        if issubclass(type_, enum.Enum):
            # Create dynamic strawberry enum
            return strawberry.enum(type_, name=f"{name_prefix}{type_.__name__}Enum")
        if issubclass(type_, msgspec.Struct):
            # Create dynamic strawberry type
            fields = {}
            for field in msgspec.structs.fields(type_):
                field_type = _convert_msgspec_to_strawberry(
                    field.type, f"{name_prefix}{type_.__name__}"
                )
                # Handle optional fields in msgspec
                if not field.required:
                    if (
                        get_origin(field_type) is not Optional
                    ):  # Check if not already optional
                        field_type = Optional[field_type]

                fields[field.name] = field_type

            type_name = f"{name_prefix}{type_.__name__}GraphQL"
            return strawberry.type(type(type_name, (), {"__annotations__": fields}))

    return JSON


class GraphQLRouteTemplate(BaseRouteTemplate, Generic[T]):
    """GraphQL 路由模板"""

    def apply(
        self,
        model_name: str,
        resource_manager: IResourceManager[T],
        router: APIRouter,
    ) -> None:
        try:
            # 1. Create dynamic types
            resource_type = resource_manager.resource_type

            # Try to convert the resource type to a strawberry type
            try:
                GraphQLData = _convert_msgspec_to_strawberry(resource_type, model_name)
            except Exception:
                # Fallback to JSON if conversion fails
                GraphQLData = JSON

            @strawberry.type(name=f"{model_name}Resource")
            class GraphQLResource:
                info: GraphQLRevisionInfo
                meta: GraphQLResourceMeta
                data: GraphQLData  # type: ignore

            # 2. Define Resolvers
            async def resolve_get_resource(
                resource_id: str,
                revision_id: Optional[str] = None,
                info: Info = None,
            ) -> Optional[GraphQLResource]:
                context = info.context
                user = context["user"]
                now = context["now"]

                try:
                    with resource_manager.meta_provide(user, now):
                        # Fetch meta first
                        meta = resource_manager.get_meta(resource_id)

                        target_revision_id = revision_id or meta.current_revision_id

                        # Check if we can use partial
                        # For now, we fetch full resource.
                        # Optimization: Inspect info.selected_fields to see if we only need data or info or meta

                        resource = resource_manager.get_resource_revision(
                            resource_id, target_revision_id
                        )

                        return GraphQLResource(
                            info=GraphQLRevisionInfo(
                                **msgspec.structs.asdict(resource.info)
                            ),
                            meta=GraphQLResourceMeta(**msgspec.structs.asdict(meta)),
                            data=resource.data
                            if GraphQLData is not JSON
                            else msgspec.to_builtins(
                                resource.data, builtin_types=(enum.Enum,)
                            ),
                        )
                except Exception:
                    return None

            async def resolve_list_resources(
                query: Optional[SearchQueryInput] = None,
                info: Info = None,
            ) -> list[GraphQLResource]:
                context = info.context
                user = context["user"]
                now = context["now"]

                search_query = ResourceMetaSearchQuery()
                if query:
                    if query.is_deleted is not None:
                        search_query.is_deleted = query.is_deleted
                    if query.created_time_start:
                        search_query.created_time_start = query.created_time_start
                    if query.created_time_end:
                        search_query.created_time_end = query.created_time_end
                    if query.updated_time_start:
                        search_query.updated_time_start = query.updated_time_start
                    if query.updated_time_end:
                        search_query.updated_time_end = query.updated_time_end
                    if query.created_bys:
                        search_query.created_bys = query.created_bys
                    if query.updated_bys:
                        search_query.updated_bys = query.updated_bys
                    if query.limit:
                        search_query.limit = query.limit
                    if query.offset:
                        search_query.offset = query.offset

                    if query.data_conditions:
                        conditions = []
                        for cond in query.data_conditions:
                            conditions.append(
                                DataSearchCondition(
                                    field_path=cond.field_path,
                                    operator=DataSearchOperator(cond.operator.value),
                                    value=cond.value,
                                )
                            )
                        search_query.data_conditions = conditions

                    if query.sorts:
                        sorts = []
                        for sort in query.sorts:
                            direction = ResourceMetaSortDirection(sort.direction.value)
                            if sort.type == GraphQLSortType.meta and sort.key:
                                sorts.append(
                                    ResourceMetaSearchSort(
                                        direction=direction,
                                        key=ResourceMetaSortKey(sort.key.value),
                                    )
                                )
                            elif sort.type == GraphQLSortType.data and sort.field_path:
                                sorts.append(
                                    ResourceDataSearchSort(
                                        direction=direction, field_path=sort.field_path
                                    )
                                )
                        search_query.sorts = sorts

                try:
                    with resource_manager.meta_provide(user, now):
                        metas = resource_manager.search_resources(search_query)
                        results = []
                        for meta in metas:
                            try:
                                resource = resource_manager.get_resource_revision(
                                    meta.resource_id, meta.current_revision_id
                                )
                                results.append(
                                    GraphQLResource(
                                        info=GraphQLRevisionInfo(
                                            **msgspec.structs.asdict(resource.info)
                                        ),
                                        meta=GraphQLResourceMeta(
                                            **msgspec.structs.asdict(meta)
                                        ),
                                        data=resource.data
                                        if GraphQLData is not JSON
                                        else msgspec.to_builtins(
                                            resource.data, builtin_types=(enum.Enum,)
                                        ),
                                    )
                                )
                            except Exception:
                                continue
                        return results
                except Exception:
                    return []

            # 3. Create Query
            query_annotations = {
                model_name: Optional[GraphQLResource],
                f"{model_name}_list": list[GraphQLResource],
            }

            query_methods = {
                model_name: strawberry.field(resolver=resolve_get_resource),
                f"{model_name}_list": strawberry.field(resolver=resolve_list_resources),
            }

            Query = type(
                "Query", (), {"__annotations__": query_annotations, **query_methods}
            )

            Query = strawberry.type(name="Query")(Query)

            # 4. Create Schema and Router
            schema = strawberry.Schema(query=Query)

            async def get_context(
                user: str = Depends(self.deps.get_user),
                now: dt.datetime = Depends(self.deps.get_now),
            ):
                return {"user": user, "now": now}

            graphql_app = GraphQLRouter(schema, context_getter=get_context)

            # Mount at /{model_name}/graphql
            router.include_router(
                graphql_app,
                prefix=f"/{model_name}/graphql",
                tags=[f"{model_name} GraphQL"],
            )
        except Exception:
            # Log error or re-raise depending on policy.
            # Since AutoCRUD swallows exceptions, we might want to log it if we had a logger.
            # For now, just re-raise so it can be caught by AutoCRUD loop (which swallows it)
            # or seen if called manually.
            raise

        # 2. Define Resolvers
        async def resolve_get_resource(
            resource_id: str,
            revision_id: Optional[str] = None,
            info: Info = None,
        ) -> Optional[GraphQLResource]:
            context = info.context
            user = context["user"]
            now = context["now"]

            try:
                with resource_manager.meta_provide(user, now):
                    # Fetch meta first
                    meta = resource_manager.get_meta(resource_id)

                    target_revision_id = revision_id or meta.current_revision_id

                    # Check if we can use partial
                    # For now, we fetch full resource.
                    # Optimization: Inspect info.selected_fields to see if we only need data or info or meta

                    resource = resource_manager.get_resource_revision(
                        resource_id, target_revision_id
                    )

                    return GraphQLResource(
                        info=GraphQLRevisionInfo(
                            **msgspec.structs.asdict(resource.info)
                        ),
                        meta=GraphQLResourceMeta(**msgspec.structs.asdict(meta)),
                        data=resource.data
                        if GraphQLData is not JSON
                        else msgspec.to_builtins(resource.data),
                    )
            except Exception:
                return None

        async def resolve_list_resources(
            query: Optional[SearchQueryInput] = None,
            info: Info = None,
        ) -> list[GraphQLResource]:
            context = info.context
            user = context["user"]
            now = context["now"]

            search_query = ResourceMetaSearchQuery()
            if query:
                if query.is_deleted is not None:
                    search_query.is_deleted = query.is_deleted
                if query.created_time_start:
                    search_query.created_time_start = query.created_time_start
                if query.created_time_end:
                    search_query.created_time_end = query.created_time_end
                if query.updated_time_start:
                    search_query.updated_time_start = query.updated_time_start
                if query.updated_time_end:
                    search_query.updated_time_end = query.updated_time_end
                if query.created_bys:
                    search_query.created_bys = query.created_bys
                if query.updated_bys:
                    search_query.updated_bys = query.updated_bys
                if query.limit:
                    search_query.limit = query.limit
                if query.offset:
                    search_query.offset = query.offset

                if query.data_conditions:
                    conditions = []
                    for cond in query.data_conditions:
                        conditions.append(
                            DataSearchCondition(
                                field_path=cond.field_path,
                                operator=DataSearchOperator(cond.operator.value),
                                value=cond.value,
                            )
                        )
                    search_query.data_conditions = conditions

                if query.sorts:
                    sorts = []
                    for sort in query.sorts:
                        direction = ResourceMetaSortDirection(sort.direction.value)
                        if sort.type == GraphQLSortType.meta and sort.key:
                            sorts.append(
                                ResourceMetaSearchSort(
                                    direction=direction,
                                    key=ResourceMetaSortKey(sort.key.value),
                                )
                            )
                        elif sort.type == GraphQLSortType.data and sort.field_path:
                            sorts.append(
                                ResourceDataSearchSort(
                                    direction=direction, field_path=sort.field_path
                                )
                            )
                    search_query.sorts = sorts

            try:
                with resource_manager.meta_provide(user, now):
                    metas = resource_manager.search_resources(search_query)
                    results = []
                    for meta in metas:
                        try:
                            resource = resource_manager.get_resource_revision(
                                meta.resource_id, meta.current_revision_id
                            )
                            results.append(
                                GraphQLResource(
                                    info=GraphQLRevisionInfo(
                                        **msgspec.structs.asdict(resource.info)
                                    ),
                                    meta=GraphQLResourceMeta(
                                        **msgspec.structs.asdict(meta)
                                    ),
                                    data=resource.data
                                    if GraphQLData is not JSON
                                    else msgspec.to_builtins(resource.data),
                                )
                            )
                        except Exception:
                            continue
                    return results
            except Exception:
                return []

        # 3. Create Query
        @strawberry.type
        class Query:
            pass

        # Dynamically add fields to Query
        setattr(Query, model_name, strawberry.field(resolver=resolve_get_resource))
        setattr(
            Query,
            f"{model_name}_list",
            strawberry.field(resolver=resolve_list_resources),
        )

        # 4. Create Schema and Router
        schema = strawberry.Schema(query=Query)

        async def get_context(
            user: str = Depends(self.deps.get_user),
            now: dt.datetime = Depends(self.deps.get_now),
        ):
            return {"user": user, "now": now}

        graphql_app = GraphQLRouter(schema, context_getter=get_context)

        # Mount at /{model_name}/graphql
        router.include_router(
            graphql_app, prefix=f"/{model_name}/graphql", tags=[f"{model_name} GraphQL"]
        )
