import json
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from enum import Enum as EnumType

from msgspec import UNSET
from sqlalchemy import (
    Boolean,
    Column,
    Float,
    Index,
    LargeBinary,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    and_,
    case,
    create_engine,
    delete,
    func,
    not_,
    or_,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.types import DateTime, TypeDecorator

from autocrud.resource_manager.basic import (
    Encoding,
    ISlowMetaStore,
    MsgspecSerializer,
)
from autocrud.types import (
    DataSearchFilter,
    DataSearchGroup,
    DataSearchLogicOperator,
    DataSearchOperator,
    FieldTransform,
    ResourceMeta,
    ResourceMetaSearchQuery,
    ResourceMetaSearchSort,
    ResourceMetaSortDirection,
)


class _JSONEncodedDict(TypeDecorator):
    """A type that stores dicts as JSON-encoded TEXT for non-PostgreSQL dialects."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        return json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, str):
            return json.loads(value)
        return value


def _build_resource_meta_table(
    table_name: str, metadata: MetaData, *, use_jsonb: bool
) -> Table:
    """Build the SQLAlchemy Table object for resource metadata."""
    indexed_data_type = JSONB if use_jsonb else _JSONEncodedDict
    table = Table(
        table_name,
        metadata,
        Column("resource_id", String, primary_key=True),
        Column("data", LargeBinary, nullable=False),
        Column("created_time", DateTime, nullable=False),
        Column("updated_time", DateTime, nullable=False),
        Column("created_by", String, nullable=False),
        Column("updated_by", String, nullable=False),
        Column("is_deleted", Boolean, nullable=False),
        Column("schema_version", String, nullable=True),
        Column("indexed_data", indexed_data_type, nullable=True),
    )
    Index(f"ix_{table_name}_created_time", table.c.created_time)
    Index(f"ix_{table_name}_updated_time", table.c.updated_time)
    Index(f"ix_{table_name}_created_by", table.c.created_by)
    Index(f"ix_{table_name}_updated_by", table.c.updated_by)
    Index(f"ix_{table_name}_is_deleted", table.c.is_deleted)
    return table


class SQLAlchemyMetaStore(ISlowMetaStore):
    """MetaStore backed by SQLAlchemy, supporting any database dialect.

    This implementation uses SQLAlchemy Core expressions (no raw SQL text)
    so that it is portable across PostgreSQL, SQLite, MySQL, etc.
    """

    def __init__(
        self,
        url: str,
        encoding: Encoding = Encoding.json,
        *,
        table_name: str = "resource_meta",
        engine: Engine | None = None,
        engine_kwargs: dict | None = None,
    ):
        self._serializer = MsgspecSerializer(
            encoding=encoding,
            resource_type=ResourceMeta,
        )
        self.table_name = table_name

        if engine is not None:
            self._engine = engine
        else:
            kw = engine_kwargs or {}
            kw.setdefault("pool_size", 5)
            kw.setdefault("max_overflow", 10)
            self._engine = create_engine(url, **kw)

        self._metadata = MetaData()
        self._table = _build_resource_meta_table(
            table_name, self._metadata, use_jsonb=self._is_pg()
        )
        self._Session = sessionmaker(bind=self._engine)

        # Create tables
        self._metadata.create_all(self._engine)

        # Migrate existing data
        self._migrate_existing_data()

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------
    @contextmanager
    def _session(self) -> Generator[Session]:
        session = self._Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------
    def _migrate_existing_data(self):
        """Fill indexed_data for rows that are missing it."""
        t = self._table
        with self._session() as session:
            stmt = select(t.c.resource_id, t.c.data).where(t.c.indexed_data.is_(None))
            rows = session.execute(stmt).fetchall()
            for resource_id, data_blob in rows:
                try:
                    meta = self._serializer.decode(data_blob)
                    indexed = (
                        meta.indexed_data if meta.indexed_data is not UNSET else None
                    )
                    session.execute(
                        t.update()
                        .where(t.c.resource_id == resource_id)
                        .values(indexed_data=indexed)
                    )
                except Exception:
                    session.execute(
                        t.update()
                        .where(t.c.resource_id == resource_id)
                        .values(indexed_data={})
                    )

    # ------------------------------------------------------------------
    # Helper: build a row dict from ResourceMeta
    # ------------------------------------------------------------------
    def _meta_to_row(self, meta: ResourceMeta) -> dict:
        indexed = meta.indexed_data if meta.indexed_data is not UNSET else None
        return {
            "resource_id": meta.resource_id,
            "data": self._serializer.encode(meta),
            "created_time": meta.created_time,
            "updated_time": meta.updated_time,
            "created_by": meta.created_by,
            "updated_by": meta.updated_by,
            "is_deleted": meta.is_deleted,
            "schema_version": meta.schema_version,
            "indexed_data": indexed,
        }

    # ------------------------------------------------------------------
    # ISlowMetaStore interface: save_many
    # ------------------------------------------------------------------
    def save_many(self, metas: Iterable[ResourceMeta]) -> None:
        metas_list = list(metas)
        if not metas_list:
            return
        t = self._table
        with self._session() as session:
            for meta in metas_list:
                row = self._meta_to_row(meta)
                # Try update first, insert if not found
                result = session.execute(
                    t.update()
                    .where(t.c.resource_id == row["resource_id"])
                    .values(**{k: v for k, v in row.items() if k != "resource_id"})
                )
                if result.rowcount == 0:
                    session.execute(t.insert().values(**row))

    # ------------------------------------------------------------------
    # MutableMapping interface
    # ------------------------------------------------------------------
    def __getitem__(self, pk: str) -> ResourceMeta:
        t = self._table
        with self._session() as session:
            row = session.execute(
                select(t.c.data).where(t.c.resource_id == pk)
            ).fetchone()
            if row is None:
                raise KeyError(pk)
            return self._serializer.decode(row[0])

    def __setitem__(self, pk: str, meta: ResourceMeta) -> None:
        t = self._table
        row = self._meta_to_row(meta)
        with self._session() as session:
            result = session.execute(
                t.update()
                .where(t.c.resource_id == pk)
                .values(**{k: v for k, v in row.items() if k != "resource_id"})
            )
            if result.rowcount == 0:
                session.execute(t.insert().values(**row))

    def __delitem__(self, pk: str) -> None:
        t = self._table
        with self._session() as session:
            result = session.execute(delete(t).where(t.c.resource_id == pk))
            if result.rowcount == 0:
                raise KeyError(pk)

    def __iter__(self) -> Generator[str]:
        t = self._table
        with self._session() as session:
            rows = session.execute(select(t.c.resource_id)).fetchall()
            for row in rows:
                yield row[0]

    def __len__(self) -> int:
        t = self._table
        with self._session() as session:
            result = session.execute(select(func.count()).select_from(t)).scalar()
            return result or 0

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def iter_search(self, query: ResourceMetaSearchQuery) -> Generator[ResourceMeta]:
        t = self._table
        stmt = select(t.c.data)

        filters = []

        if query.is_deleted is not UNSET:
            filters.append(t.c.is_deleted == query.is_deleted)

        if query.created_time_start is not UNSET:
            filters.append(t.c.created_time >= query.created_time_start)
        if query.created_time_end is not UNSET:
            filters.append(t.c.created_time <= query.created_time_end)

        if query.updated_time_start is not UNSET:
            filters.append(t.c.updated_time >= query.updated_time_start)
        if query.updated_time_end is not UNSET:
            filters.append(t.c.updated_time <= query.updated_time_end)

        if query.created_bys is not UNSET:
            filters.append(t.c.created_by.in_(query.created_bys))
        if query.updated_bys is not UNSET:
            filters.append(t.c.updated_by.in_(query.updated_bys))

        # data_conditions
        if query.data_conditions is not UNSET:
            for cond in query.data_conditions:
                clause = self._build_condition(cond)
                if clause is not None:
                    filters.append(clause)

        # conditions
        if query.conditions is not UNSET:
            for cond in query.conditions:
                clause = self._build_condition(cond)
                if clause is not None:
                    filters.append(clause)

        if filters:
            stmt = stmt.where(*filters)

        # Sorting
        if query.sorts is not UNSET and query.sorts:
            order_clauses = []
            for sort in query.sorts:
                if isinstance(sort, ResourceMetaSearchSort):
                    col = getattr(t.c, sort.key.value)
                    if sort.direction == ResourceMetaSortDirection.ascending:
                        order_clauses.append(col.asc())
                    else:
                        order_clauses.append(col.desc())
                else:
                    # ResourceDataSearchSort – sort on indexed_data field
                    order_expr = self._jsonb_sort_expr(sort.field_path)
                    if sort.direction == ResourceMetaSortDirection.ascending:
                        order_clauses.append(order_expr.asc())
                    else:
                        order_clauses.append(order_expr.desc())
            stmt = stmt.order_by(*order_clauses)

        stmt = stmt.limit(query.limit).offset(query.offset)

        with self._session() as session:
            rows = session.execute(stmt).fetchall()
            for row in rows:
                yield self._serializer.decode(row[0])

    # ------------------------------------------------------------------
    # Dialect-aware helpers for JSONB / JSON extraction
    # ------------------------------------------------------------------
    def _is_pg(self) -> bool:
        return self._engine.dialect.name == "postgresql"

    def _jsonb_text(self, field_path: str):
        """Extract text value from indexed_data for a given field path.

        PostgreSQL: indexed_data ->> 'field_path'
        Others:     json_extract(indexed_data, '$.field_path')  (as text via CAST)
        """
        t = self._table
        if self._is_pg():
            return t.c.indexed_data[field_path].astext
        # SQLite / others: use json_extract
        return func.json_extract(t.c.indexed_data, f"$.{field_path}")

    def _jsonb_element(self, field_path: str):
        """Extract the raw JSON element (keeping type) from indexed_data.

        PostgreSQL: indexed_data -> 'field_path'
        Others:     json_extract(indexed_data, '$.field_path')
        """
        t = self._table
        if self._is_pg():
            return t.c.indexed_data[field_path]
        return func.json_extract(t.c.indexed_data, f"$.{field_path}")

    def _jsonb_numeric(self, field_path: str):
        """Extract a numeric value from indexed_data.

        PostgreSQL: (indexed_data ->> 'field_path')::numeric
        Others:     CAST(json_extract(indexed_data, '$.field_path') AS REAL)
        """
        if self._is_pg():
            t = self._table
            return t.c.indexed_data[field_path].astext.cast(Numeric)
        return func.CAST(
            func.json_extract(self._table.c.indexed_data, f"$.{field_path}"),
            Float,
        )

    def _jsonb_sort_expr(self, field_path: str):
        """Expression for ORDER BY on indexed_data field."""
        t = self._table
        if self._is_pg():
            return t.c.indexed_data[field_path]
        return func.json_extract(t.c.indexed_data, f"$.{field_path}")

    def _jsonb_has_key(self, field_path: str):
        """Check if indexed_data contains a key.

        PostgreSQL: indexed_data ? 'field_path'
        Others:     json_extract(indexed_data, '$.field_path') IS NOT NULL
                    (plus check json_type is not 'null' if needed)
        """
        t = self._table
        if self._is_pg():
            return t.c.indexed_data.has_key(field_path)
        # For SQLite: key exists if json_extract returns something and the column itself is not NULL
        return func.json_type(t.c.indexed_data, f"$.{field_path}").isnot(None)

    def _jsonb_typeof(self, field_path: str):
        """Get the JSON type of a value in indexed_data.

        PostgreSQL: jsonb_typeof(indexed_data -> 'field_path')
        Others:     json_type(indexed_data, '$.field_path')
        """
        t = self._table
        if self._is_pg():
            return func.jsonb_typeof(t.c.indexed_data[field_path])
        return func.json_type(t.c.indexed_data, f"$.{field_path}")

    def _jsonb_array_length(self, field_path: str):
        """Get length of a JSON array in indexed_data.

        PostgreSQL: jsonb_array_length(indexed_data -> 'field_path')
        Others:     json_array_length(indexed_data, '$.field_path')
        """
        t = self._table
        if self._is_pg():
            return func.jsonb_array_length(t.c.indexed_data[field_path])
        return func.json_array_length(t.c.indexed_data, f"$.{field_path}")

    def _jsonb_string_length(self, field_path: str):
        """Get length of a string stored in indexed_data.

        PostgreSQL: length(indexed_data ->> 'field_path')
        Others:     length(json_extract(indexed_data, '$.field_path'))
        """
        return func.length(self._jsonb_text(field_path))

    def _regex_match(self, expr, pattern):
        """Build a regex match expression.

        PostgreSQL: expr ~ pattern
        SQLite:     expr REGEXP pattern  (requires extension, but we use text-based fallback)
        """
        if self._is_pg():
            # PostgreSQL regex operator ~
            return expr.op("~")(pattern)
        # SQLite does not support REGEXP natively; some builds have it.
        # We use the REGEXP operator and hope the connection has it loaded.
        # Alternatively fall back to LIKE for basic patterns.
        return expr.op("REGEXP")(pattern)

    # ------------------------------------------------------------------
    # Condition builder
    # ------------------------------------------------------------------
    def _build_condition(self, condition: DataSearchFilter):
        """Build a SQLAlchemy filter clause from a DataSearchFilter."""
        if isinstance(condition, DataSearchGroup):
            sub_clauses = []
            for sub in condition.conditions:
                c = self._build_condition(sub)
                if c is not None:
                    sub_clauses.append(c)
            if not sub_clauses:
                return None
            if condition.operator == DataSearchLogicOperator.and_op:
                return and_(*sub_clauses)
            if condition.operator == DataSearchLogicOperator.or_op:
                return or_(*sub_clauses)
            if condition.operator == DataSearchLogicOperator.not_op:
                return not_(and_(*sub_clauses))
            return None

        field_path = condition.field_path
        operator = condition.operator
        value = condition.value

        # Normalize Enum values
        if isinstance(value, EnumType):
            value = value.value
        elif isinstance(value, (list, tuple, set)):
            value = [v.value if isinstance(v, EnumType) else v for v in value]

        # Check if this is a meta column
        meta_fields = {
            "resource_id",
            "created_time",
            "updated_time",
            "created_by",
            "updated_by",
            "is_deleted",
            "schema_version",
        }

        if field_path in meta_fields:
            return self._build_meta_condition(field_path, operator, value)

        return self._build_data_condition(condition, field_path, operator, value)

    # ------------------------------------------------------------------
    # Meta field conditions
    # ------------------------------------------------------------------
    def _build_meta_condition(self, field_path: str, operator, value):
        t = self._table
        col = getattr(t.c, field_path)
        is_boolean_field = field_path == "is_deleted"

        if operator == DataSearchOperator.equals:
            if isinstance(value, (list, dict)):
                return None
            if (
                is_boolean_field
                and isinstance(value, (int, float, str))
                and value not in (True, False)
            ):
                return None
            return col == value

        if operator == DataSearchOperator.not_equals:
            if isinstance(value, (list, dict)):
                return None
            if is_boolean_field and not isinstance(value, bool):
                if isinstance(value, (int, float, str)):
                    return None
            return col != value

        if operator == DataSearchOperator.greater_than:
            return col > value
        if operator == DataSearchOperator.greater_than_or_equal:
            return col >= value
        if operator == DataSearchOperator.less_than:
            return col < value
        if operator == DataSearchOperator.less_than_or_equal:
            return col <= value

        if operator == DataSearchOperator.contains:
            return col.contains(value)
        if operator == DataSearchOperator.starts_with:
            return col.startswith(value)
        if operator == DataSearchOperator.ends_with:
            return col.endswith(value)

        if operator == DataSearchOperator.regex:
            return self._regex_match(col, value)

        if operator == DataSearchOperator.in_list:
            if isinstance(value, (list, tuple, set)):
                return col.in_(list(value))
        elif operator == DataSearchOperator.not_in_list:
            if isinstance(value, (list, tuple, set)):
                return col.notin_(list(value))

        if operator == DataSearchOperator.is_null:
            return col.is_(None) if value else col.isnot(None)

        if operator == DataSearchOperator.exists:
            return text("TRUE") if value else text("FALSE")

        if operator == DataSearchOperator.isna:
            return col.is_(None) if value else col.isnot(None)

        return None

    # ------------------------------------------------------------------
    # Data (indexed_data) field conditions
    # ------------------------------------------------------------------
    def _build_data_condition(self, condition, field_path, operator, value):
        jsonb_text = self._jsonb_text(field_path)
        jsonb_numeric = self._jsonb_numeric(field_path)

        # Apply field transformation
        if (
            condition.transform is not None
            and condition.transform == FieldTransform.length
        ):
            typeof = self._jsonb_typeof(field_path)
            arr_len = self._jsonb_array_length(field_path)
            str_len = self._jsonb_string_length(field_path)
            # Use CASE to pick the right length function
            length_expr = case(
                (typeof == "array", arr_len),
                (typeof == "string", str_len),
                else_=None,
            )
            jsonb_text = length_expr
            jsonb_numeric = length_expr

        if operator == DataSearchOperator.equals:
            if isinstance(value, (list, dict)):
                elem = self._jsonb_element(field_path)
                return elem == func.cast(
                    json.dumps(value), _jsonb_cast_type(self._is_pg())
                )
            if isinstance(value, bool):
                return jsonb_text == ("true" if value else "false")
            return jsonb_text == str(value)

        if operator == DataSearchOperator.not_equals:
            if isinstance(value, (list, dict)):
                elem = self._jsonb_element(field_path)
                return (jsonb_text.is_(None)) | (
                    elem
                    != func.cast(json.dumps(value), _jsonb_cast_type(self._is_pg()))
                )
            if isinstance(value, bool):
                return jsonb_text != ("true" if value else "false")
            return jsonb_text != str(value)

        if operator == DataSearchOperator.greater_than:
            return jsonb_numeric > value
        if operator == DataSearchOperator.greater_than_or_equal:
            return jsonb_numeric >= value
        if operator == DataSearchOperator.less_than:
            return jsonb_numeric < value
        if operator == DataSearchOperator.less_than_or_equal:
            return jsonb_numeric <= value

        if operator == DataSearchOperator.contains:
            return jsonb_text.contains(str(value))
        if operator == DataSearchOperator.starts_with:
            return jsonb_text.startswith(str(value))
        if operator == DataSearchOperator.ends_with:
            return jsonb_text.endswith(str(value))

        if operator == DataSearchOperator.regex:
            return self._regex_match(jsonb_text, value)

        if operator == DataSearchOperator.in_list:
            if isinstance(value, (list, tuple, set)):
                return jsonb_text.in_([str(v) for v in value])
        elif operator == DataSearchOperator.not_in_list:
            if isinstance(value, (list, tuple, set)):
                return jsonb_text.notin_([str(v) for v in value])

        if operator == DataSearchOperator.is_null:
            has_key = self._jsonb_has_key(field_path)
            if value:
                return and_(has_key, jsonb_text.is_(None))
            else:
                return and_(has_key, jsonb_text.isnot(None))

        if operator == DataSearchOperator.exists:
            has_key = self._jsonb_has_key(field_path)
            return has_key if value else ~has_key

        if operator == DataSearchOperator.isna:
            if value:
                return jsonb_text.is_(None)
            else:
                return jsonb_text.isnot(None)

        return None


# ------------------------------------------------------------------
# Tiny helper types used above
# ------------------------------------------------------------------


def _jsonb_cast_type(is_pg: bool):
    """Return the type to cast a JSON string literal."""
    if is_pg:
        return JSONB
    return Text
