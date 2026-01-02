import datetime as dt
import enum
import inspect
from typing import Any, Generic, Optional, TypeVar, get_args, get_origin

import msgspec
import strawberry
from strawberry.tools import create_type
from strawberry.utils.str_converters import to_snake_case, to_camel_case
from fastapi import APIRouter, Depends
from strawberry.fastapi import GraphQLRouter
from strawberry.scalars import JSON
from strawberry.types import Info

from autocrud.crud.route_templates.basic import BaseRouteTemplate, DependencyProvider
from autocrud.types import (
    DataSearchCondition,
    DataSearchOperator,
    DataSearchGroup,
    DataSearchLogicOperator,
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
    regex = "regex"
    in_list = "in"
    not_in_list = "not_in"


@strawberry.enum
class GraphQLDataSearchLogicOperator(str, enum.Enum):
    and_op = "and"
    or_op = "or"
    not_op = "not"


@strawberry.input
class DataSearchConditionInput:
    field_path: str
    operator: GraphQLDataSearchOperator
    value: JSON


@strawberry.input
class DataSearchGroupInput:
    operator: GraphQLDataSearchLogicOperator
    conditions: list["DataSearchFilterInput"]


@strawberry.input
class DataSearchFilterInput:
    condition: Optional[DataSearchConditionInput] = None
    group: Optional[DataSearchGroupInput] = None


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
    data_conditions: Optional[list[DataSearchFilterInput]] = None
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
            annotations = {}
            attributes = {}
            field_map = {}
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

                # Calculate GraphQL name and store mapping
                graphql_name = to_camel_case(field.name)
                field_map[graphql_name] = field.name

                annotations[field.name] = field_type
                attributes[field.name] = strawberry.field(name=graphql_name)

            type_name = f"{name_prefix}{type_.__name__}GraphQL"
            cls = type(type_name, (), {**attributes, "__annotations__": annotations})
            cls._field_map = field_map
            return strawberry.type(cls)

    return JSON


def _unwrap_type(type_):
    origin = get_origin(type_)
    args = get_args(type_)

    if origin is list or origin is list:
        return _unwrap_type(args[0])
    if origin is Optional:
        return _unwrap_type(args[0])
    # Handle Union[T, None] which is Optional
    if origin is not None and type(None) in args:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _unwrap_type(non_none[0])

    return type_


def _extract_selections(selections, type_: Any = None, parent_path="") -> list[str]:
    fields = []

    # Get field map if available
    field_map = getattr(type_, "_field_map", {})
    # Get type definition for looking up field types
    type_def = getattr(type_, "__strawberry_definition__", None)

    for selection in selections:
        if selection.name == "__typename":
            continue

        # Resolve python name
        if field_map:
            snake_name = field_map.get(selection.name)
            if not snake_name:
                snake_name = to_snake_case(selection.name)
        else:
            snake_name = to_snake_case(selection.name)

        current_path = f"{parent_path}/{snake_name}" if parent_path else snake_name

        if selection.selections:
            next_type = None
            if type_def:
                # Find field definition (internal name matches snake_name)
                field_def = next(
                    (f for f in type_def.fields if f.name == snake_name), None
                )
                if field_def:
                    next_type = _unwrap_type(field_def.type)

            fields.extend(
                _extract_selections(selection.selections, next_type, current_path)
            )
        else:
            fields.append(current_path)
    return fields


def _get_list_depth(type_: Any) -> int:
    depth = 0
    while get_origin(type_) is list or get_origin(type_) is list:
        depth += 1
        type_ = get_args(type_)[0]
    return depth


def _convert_filter_input(
    input_filter: DataSearchFilterInput,
) -> DataSearchCondition | DataSearchGroup | None:
    if input_filter.group:
        # It's a group
        if not input_filter.group.conditions:
            return None

        conditions = []
        for f in input_filter.group.conditions:
            c = _convert_filter_input(f)
            if c:
                conditions.append(c)

        if not conditions:
            return None

        return DataSearchGroup(
            operator=DataSearchLogicOperator(input_filter.group.operator.value),
            conditions=conditions,
        )
    elif input_filter.condition:
        # It's a condition
        return DataSearchCondition(
            field_path=input_filter.condition.field_path,
            operator=DataSearchOperator(input_filter.condition.operator.value),
            value=input_filter.condition.value,
        )
    return None


class GraphQLRouteTemplate(BaseRouteTemplate, Generic[T]):
    """GraphQL 路由模板"""

    def __init__(self, dependency_provider: DependencyProvider = None):
        super().__init__(dependency_provider)
        self.resources: dict[str, IResourceManager] = {}
        self.graphql_router: Optional[GraphQLRouter] = None
        self.mounted = False

    def apply(
        self,
        model_name: str,
        resource_manager: IResourceManager[T],
        router: APIRouter,
    ) -> None:
        self.resources[model_name] = resource_manager

        # Build/Update Schema
        schema = self._build_schema()

        if not self.mounted:
            # First time: create router and mount it
            async def get_context(
                user: str = Depends(self.deps.get_user),
                now: dt.datetime = Depends(self.deps.get_now),
            ):
                return {"user": user, "now": now}

            self.graphql_router = GraphQLRouter(schema, context_getter=get_context)
            router.include_router(
                self.graphql_router, prefix="/graphql", tags=["GraphQL"]
            )
            self.mounted = True
        else:
            # Update schema on existing router
            self.graphql_router.schema = schema

    def _build_schema(self) -> strawberry.Schema:
        fields = []

        for model_name, resource_manager in self.resources.items():
            try:
                # Sanitize model_name for GraphQL (replace - with _)
                safe_model_name = model_name.replace("-", "_")

                # 1. Create dynamic types
                resource_type = resource_manager.resource_type

                # Try to convert the resource type to a strawberry type
                try:
                    GraphQLData = _convert_msgspec_to_strawberry(
                        resource_type, safe_model_name
                    )
                except Exception:
                    # Fallback to JSON if conversion fails
                    GraphQLData = JSON

                @strawberry.type(name=f"{safe_model_name}Resource")
                class Resource:
                    info: GraphQLRevisionInfo
                    meta: GraphQLResourceMeta
                    data: GraphQLData  # type: ignore

                # Rename class to avoid confusion
                Resource.__name__ = f"{safe_model_name}Resource"

                # 2. Define Resolvers
                def make_resolvers(rm: IResourceManager, gql_data: type):
                    async def resolve_get_resource(
                        resource_id: str,
                        revision_id: Optional[str] = None,
                        info: Info = None,
                    ) -> Optional[Resource]:
                        context = info.context
                        user = context["user"]
                        now = context["now"]

                        try:
                            with rm.meta_provide(user, now):
                                # Fetch meta first
                                meta = rm.get_meta(resource_id)

                                target_revision_id = (
                                    revision_id or meta.current_revision_id
                                )

                                data_obj = None
                                info_obj = None

                                # Check data selection
                                current_field = next(
                                    (
                                        f
                                        for f in info.selected_fields
                                        if f.name == info.field_name
                                    ),
                                    None,
                                )

                                data_field = None
                                info_field = None

                                if current_field:
                                    data_field = next(
                                        (
                                            f
                                            for f in current_field.selections
                                            if f.name == "data"
                                        ),
                                        None,
                                    )
                                    info_field = next(
                                        (
                                            f
                                            for f in current_field.selections
                                            if f.name == "info"
                                        ),
                                        None,
                                    )

                                if data_field:
                                    if data_field.selections:
                                        partial_fields = _extract_selections(
                                            data_field.selections, gql_data
                                        )
                                        if partial_fields:
                                            # Handle list types
                                            depth = _get_list_depth(rm.resource_type)
                                            if depth > 0:
                                                prefix = "/".join(["*"] * depth)
                                                partial_fields = [
                                                    f"{prefix}/{f}"
                                                    for f in partial_fields
                                                ]

                                            data_obj = rm.get_partial(
                                                resource_id,
                                                target_revision_id,
                                                partial_fields,
                                            )
                                        else:
                                            # Should not happen for object types with selections
                                            resource = rm.get_resource_revision(
                                                resource_id, target_revision_id
                                            )
                                            data_obj = resource.data
                                            info_obj = resource.info
                                    else:
                                        # Scalar (JSON) or no sub-selections
                                        resource = rm.get_resource_revision(
                                            resource_id, target_revision_id
                                        )
                                        data_obj = resource.data
                                        info_obj = resource.info

                                # Check info selection
                                if info_field and info_obj is None:
                                    info_obj = rm.get_revision_info(
                                        resource_id, target_revision_id
                                    )

                                return Resource(
                                    info=GraphQLRevisionInfo(
                                        **msgspec.structs.asdict(info_obj)
                                    )
                                    if info_obj
                                    else None,
                                    meta=GraphQLResourceMeta(
                                        **msgspec.structs.asdict(meta)
                                    ),
                                    data=data_obj
                                    if gql_data is not JSON
                                    else msgspec.to_builtins(
                                        data_obj, builtin_types=(enum.Enum,)
                                    ),
                                )
                        except Exception:
                            return None

                    async def resolve_list_resources(
                        query: Optional[SearchQueryInput] = None,
                        info: Info = None,
                    ) -> list[Resource]:
                        context = info.context
                        user = context["user"]
                        now = context["now"]

                        search_query = ResourceMetaSearchQuery()
                        if query:
                            if query.is_deleted is not None:
                                search_query.is_deleted = query.is_deleted
                            if query.created_time_start:
                                search_query.created_time_start = (
                                    query.created_time_start
                                )
                            if query.created_time_end:
                                search_query.created_time_end = query.created_time_end
                            if query.updated_time_start:
                                search_query.updated_time_start = (
                                    query.updated_time_start
                                )
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
                                    c = _convert_filter_input(cond)
                                    if c:
                                        conditions.append(c)
                                search_query.data_conditions = conditions

                            if query.sorts:
                                sorts = []
                                for sort in query.sorts:
                                    direction = ResourceMetaSortDirection(
                                        sort.direction.value
                                    )
                                    if sort.type == GraphQLSortType.meta and sort.key:
                                        sorts.append(
                                            ResourceMetaSearchSort(
                                                direction=direction,
                                                key=ResourceMetaSortKey(sort.key.value),
                                            )
                                        )
                                    elif (
                                        sort.type == GraphQLSortType.data
                                        and sort.field_path
                                    ):
                                        sorts.append(
                                            ResourceDataSearchSort(
                                                direction=direction,
                                                field_path=sort.field_path,
                                            )
                                        )
                                search_query.sorts = sorts

                        try:
                            with rm.meta_provide(user, now):
                                metas = rm.search_resources(search_query)
                                results = []

                                # Determine what to fetch based on info
                                current_field = next(
                                    (
                                        f
                                        for f in info.selected_fields
                                        if f.name == info.field_name
                                    ),
                                    None,
                                )

                                data_field = None
                                info_field = None

                                if current_field:
                                    data_field = next(
                                        (
                                            f
                                            for f in current_field.selections
                                            if f.name == "data"
                                        ),
                                        None,
                                    )
                                    info_field = next(
                                        (
                                            f
                                            for f in current_field.selections
                                            if f.name == "info"
                                        ),
                                        None,
                                    )

                                fetch_full_data = False
                                partial_fields = None

                                if data_field:
                                    if data_field.selections:
                                        partial_fields = _extract_selections(
                                            data_field.selections, gql_data
                                        )
                                        if not partial_fields:
                                            fetch_full_data = True
                                        else:
                                            # Handle list types
                                            depth = _get_list_depth(rm.resource_type)
                                            if depth > 0:
                                                prefix = "/".join(["*"] * depth)
                                                partial_fields = [
                                                    f"{prefix}/{f}"
                                                    for f in partial_fields
                                                ]
                                    else:
                                        fetch_full_data = True

                                fetch_info = bool(info_field)

                                for meta in metas:
                                    try:
                                        data_obj = None
                                        info_obj = None

                                        if fetch_full_data:
                                            resource = rm.get_resource_revision(
                                                meta.resource_id,
                                                meta.current_revision_id,
                                            )
                                            data_obj = resource.data
                                            info_obj = resource.info
                                        elif partial_fields:
                                            data_obj = rm.get_partial(
                                                meta.resource_id,
                                                meta.current_revision_id,
                                                partial_fields,
                                            )

                                        if fetch_info and info_obj is None:
                                            info_obj = rm.get_revision_info(
                                                meta.resource_id,
                                                meta.current_revision_id,
                                            )

                                        results.append(
                                            Resource(
                                                info=GraphQLRevisionInfo(
                                                    **msgspec.structs.asdict(info_obj)
                                                )
                                                if info_obj
                                                else None,
                                                meta=GraphQLResourceMeta(
                                                    **msgspec.structs.asdict(meta)
                                                ),
                                                data=data_obj
                                                if gql_data is not JSON
                                                else msgspec.to_builtins(
                                                    data_obj,
                                                    builtin_types=(enum.Enum,),
                                                ),
                                            )
                                        )
                                    except Exception:
                                        continue
                                return results
                        except Exception:
                            return []

                    return resolve_get_resource, resolve_list_resources

                resolve_get_resource, resolve_list_resources = make_resolvers(
                    resource_manager, GraphQLData
                )

                f1 = strawberry.field(
                    name=safe_model_name,
                    resolver=resolve_get_resource,
                )
                f1.python_name = safe_model_name
                fields.append(f1)

                f2 = strawberry.field(
                    name=f"{safe_model_name}_list",
                    resolver=resolve_list_resources,
                )
                f2.python_name = f"{safe_model_name}_list"
                fields.append(f2)

            except Exception:
                continue

        if not fields:
            # Create a dummy query if no fields to avoid crash
            @strawberry.type
            class Query:
                @strawberry.field
                def hello(self) -> str:
                    return "world"

            return strawberry.Schema(query=Query)

        Query = create_type(name="Query", fields=fields)
        return strawberry.Schema(query=Query)
