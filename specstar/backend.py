from __future__ import annotations

import json
import os
from abc import ABC
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping

import msgspec
from msgspec import Struct, field

from specstar.message_queue.rabbitmq import RabbitMQMessageQueueFactory
from specstar.message_queue.simple import SimpleMessageQueueFactory
from specstar.resource_manager.basic import (
    Encoding,
    IBlobStore,
    IMetaStore,
    IResourceStore,
)
from specstar.resource_manager.blob_store.s3 import S3BlobStore
from specstar.resource_manager.blob_store.simple import DiskBlobStore, MemoryBlobStore
from specstar.resource_manager.core import SimpleStorage
from specstar.resource_manager.meta_store.postgres import PostgresMetaStore
from specstar.resource_manager.meta_store.simple import DiskMetaStore, MemoryMetaStore
from specstar.resource_manager.meta_store.sqlite3 import S3SqliteMetaStore
from specstar.resource_manager.resource_store.postgres import PostgresResourceStore
from specstar.resource_manager.resource_store.s3 import S3ResourceStore
from specstar.resource_manager.resource_store.simple import (
    DiskResourceStore,
    MemoryResourceStore,
)
from specstar.resource_manager.storage_factory import (
    DiskStorageFactory,
    IStorageFactory,
    MemoryStorageFactory,
)
from specstar.types import IMessageQueueFactory
from specstar.util.naming import NameConverter

BackendRole = Literal["meta", "resource", "blob", "mq"]


class BackendDefaults(Struct, kw_only=True, omit_defaults=True):
    """Shared defaults applied across unified backend configuration.

    These values provide the common baseline for backend providers created
    through ``BackendConfig``. Individual connection profiles or role bindings
    may still supply provider-specific options to override the shared defaults
    when needed.
    """

    encoding: Encoding = Encoding.json
    table_prefix: str = ""
    blob_prefix: str = "blobs/"
    upload_method: Literal["proxy", "single_put"] = "proxy"
    presigned_url_expiry: int = 3600


class ConnectionProfile(Struct, kw_only=True, omit_defaults=True):
    """Reusable named backend connection.

    A connection profile defines a backend ``type`` plus its provider-specific
    options once, then lets multiple backend roles reuse that definition by
    referring to it from ``BackendBinding(use=...)``.
    """

    type: str
    options: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    tags: tuple[str, ...] = ()


class BackendBinding(Struct, kw_only=True, omit_defaults=True):
    """Map one backend role to either a named connection or an inline provider.

    Bindings are used for the four SpecStar backend concerns: metadata,
    structured resource payloads, blob storage, and the message queue.
    """

    use: str | None = None
    type: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
    required: bool = True


class BackendConfig(Struct, kw_only=True, omit_defaults=True):
    """Schema-first unified backend configuration for SpecStar.

    This higher-level API lets you configure metadata, resource, blob, and
    message-queue backends together through one typed object, a plain mapping,
    or a JSON file.
    """

    version: int = 1
    defaults: BackendDefaults = field(default_factory=BackendDefaults)
    connections: dict[str, ConnectionProfile] = field(default_factory=dict)
    meta: BackendBinding = field(default_factory=lambda: BackendBinding(type="memory"))
    resource: BackendBinding = field(
        default_factory=lambda: BackendBinding(type="memory")
    )
    blob: BackendBinding = field(default_factory=lambda: BackendBinding(type="memory"))
    mq: BackendBinding | None = None

    @classmethod
    def from_json_file(cls, path: str | Path) -> "BackendConfig":
        raw = json.loads(Path(path).read_text())
        return msgspec.convert(_expand_env(raw), type=cls)

    @classmethod
    def from_value(
        cls, value: "BackendConfig | Mapping[str, Any] | str | Path"
    ) -> "BackendConfig":
        if isinstance(value, cls):
            return value
        if isinstance(value, (str, Path)):
            return cls.from_json_file(value)
        if isinstance(value, Mapping):
            return msgspec.convert(_expand_env(dict(value)), type=cls)
        raise TypeError(f"Unsupported backend config value: {type(value)!r}")


class BackendProvider(ABC):
    """Pluggable provider for unified backend configuration."""

    type: str = ""
    capabilities: frozenset[BackendRole] = frozenset()

    def validate(
        self,
        *,
        role: BackendRole,
        options: dict[str, Any],
        defaults: BackendDefaults,
    ) -> None:
        """Validate provider-specific options before runtime build."""

    def build_meta(
        self,
        *,
        model_name: str,
        options: dict[str, Any],
        defaults: BackendDefaults,
    ) -> IMetaStore:
        raise NotImplementedError(f"Provider {self.type!r} does not support meta")

    def build_resource(
        self,
        *,
        model_name: str,
        options: dict[str, Any],
        defaults: BackendDefaults,
    ) -> IResourceStore:
        raise NotImplementedError(f"Provider {self.type!r} does not support resource")

    def build_blob(
        self,
        *,
        options: dict[str, Any],
        defaults: BackendDefaults,
    ) -> IBlobStore:
        raise NotImplementedError(f"Provider {self.type!r} does not support blob")

    def build_mq_factory(
        self,
        *,
        options: dict[str, Any],
        defaults: BackendDefaults,
    ) -> IMessageQueueFactory:
        raise NotImplementedError(f"Provider {self.type!r} does not support mq")


class BackendRegistry:
    """Registry for built-in and custom backend providers."""

    def __init__(self):
        self._providers: dict[str, BackendProvider] = {}

    def register(self, provider: BackendProvider) -> None:
        if not provider.type:
            raise ValueError("backend provider type cannot be empty")
        self._providers[provider.type] = provider

    def get(self, type_name: str) -> BackendProvider:
        try:
            return self._providers[type_name]
        except KeyError as exc:
            raise ValueError(f"unknown backend type: {type_name}") from exc


@dataclass(slots=True)
class BackendBundle:
    config: BackendConfig | None
    storage_factory: IStorageFactory
    blob_store: IBlobStore
    message_queue_factory: IMessageQueueFactory | None


class BackendStorageFactory(IStorageFactory):
    """Storage factory built from explicit meta/resource backend bindings."""

    def __init__(self, config: BackendConfig, registry: BackendRegistry):
        self.config = config
        self.registry = registry

    def build(self, model_name: str):
        meta_store = _resolve_store_role(
            config=self.config,
            registry=self.registry,
            role="meta",
            model_name=model_name,
        )
        resource_store = _resolve_store_role(
            config=self.config,
            registry=self.registry,
            role="resource",
            model_name=model_name,
        )
        return SimpleStorage(meta_store, resource_store)


class MemoryBackendProvider(BackendProvider):
    type = "memory"
    capabilities = frozenset({"meta", "resource", "blob"})

    def build_meta(
        self, *, model_name: str, options: dict[str, Any], defaults: BackendDefaults
    ) -> IMetaStore:
        return MemoryMetaStore(encoding=defaults.encoding)

    def build_resource(
        self, *, model_name: str, options: dict[str, Any], defaults: BackendDefaults
    ) -> IResourceStore:
        return MemoryResourceStore(encoding=defaults.encoding)

    def build_blob(
        self, *, options: dict[str, Any], defaults: BackendDefaults
    ) -> IBlobStore:
        return MemoryBlobStore()


class DiskBackendProvider(BackendProvider):
    type = "disk"
    capabilities = frozenset({"meta", "resource", "blob"})

    def validate(
        self,
        *,
        role: BackendRole,
        options: dict[str, Any],
        defaults: BackendDefaults,
    ) -> None:
        self._rootdir(options)

    def _rootdir(self, options: dict[str, Any]) -> Path:
        rootdir = options.get("rootdir")
        if not rootdir:
            raise ValueError("disk backend requires options.rootdir")
        return Path(rootdir)

    def build_meta(
        self, *, model_name: str, options: dict[str, Any], defaults: BackendDefaults
    ) -> IMetaStore:
        rootdir = self._rootdir(options)
        return DiskMetaStore(
            rootdir=rootdir / model_name / "meta", encoding=defaults.encoding
        )

    def build_resource(
        self, *, model_name: str, options: dict[str, Any], defaults: BackendDefaults
    ) -> IResourceStore:
        rootdir = self._rootdir(options)
        return DiskResourceStore(
            rootdir=rootdir / model_name / "data", encoding=defaults.encoding
        )

    def build_blob(
        self, *, options: dict[str, Any], defaults: BackendDefaults
    ) -> IBlobStore:
        rootdir = self._rootdir(options)
        return DiskBlobStore(rootdir / "_blobs")


class PostgresBackendProvider(BackendProvider):
    type = "postgres"
    capabilities = frozenset({"meta", "resource"})

    def validate(
        self,
        *,
        role: BackendRole,
        options: dict[str, Any],
        defaults: BackendDefaults,
    ) -> None:
        self._dsn(options)

    def _dsn(self, options: dict[str, Any]) -> str:
        dsn = options.get("dsn") or options.get("connection_string")
        if not dsn:
            raise ValueError("postgres backend requires options.dsn")
        return str(dsn)

    def build_meta(
        self, *, model_name: str, options: dict[str, Any], defaults: BackendDefaults
    ) -> IMetaStore:
        safe_name = NameConverter(model_name).to("snake")
        table_prefix = options.get("table_prefix", defaults.table_prefix)
        table_name = (
            f"{table_prefix}{safe_name}_meta" if table_prefix else f"{safe_name}_meta"
        )
        return PostgresMetaStore(
            pg_dsn=self._dsn(options),
            encoding=options.get("encoding", defaults.encoding),
            table_name=table_name,
        )

    def build_resource(
        self, *, model_name: str, options: dict[str, Any], defaults: BackendDefaults
    ) -> IResourceStore:
        safe_name = NameConverter(model_name).to("snake")
        table_prefix = options.get("table_prefix", defaults.table_prefix)
        resource_prefix = (
            f"{table_prefix}{safe_name}_" if table_prefix else f"{safe_name}_"
        )
        return PostgresResourceStore(
            pg_dsn=self._dsn(options),
            encoding=options.get("encoding", defaults.encoding),
            table_prefix=resource_prefix,
        )


class S3BackendProvider(BackendProvider):
    type = "s3"
    capabilities = frozenset({"meta", "resource", "blob"})

    def validate(
        self,
        *,
        role: BackendRole,
        options: dict[str, Any],
        defaults: BackendDefaults,
    ) -> None:
        self._bucket(options)

    def _bucket(self, options: dict[str, Any]) -> str:
        bucket = options.get("bucket")
        if not bucket:
            raise ValueError("s3 backend requires options.bucket")
        return str(bucket)

    def _client_kwargs(self, options: dict[str, Any]) -> dict[str, Any]:
        return dict(
            options.get("client_kwargs") or options.get("s3_client_kwargs") or {}
        )

    def build_meta(
        self, *, model_name: str, options: dict[str, Any], defaults: BackendDefaults
    ) -> IMetaStore:
        prefix = options.get("prefix", "")
        model_prefix = f"{prefix}{model_name}/"
        return S3SqliteMetaStore(
            bucket=self._bucket(options),
            key=f"{model_prefix}meta.db",
            access_key_id=options.get(
                "access_key_id", options.get("s3_access_key_id", "minioadmin")
            ),
            secret_access_key=options.get(
                "secret_access_key", options.get("s3_secret_access_key", "minioadmin")
            ),
            region_name=options.get(
                "region_name", options.get("s3_region", "us-east-1")
            ),
            endpoint_url=options.get("endpoint_url", options.get("s3_endpoint_url")),
            encoding=options.get("encoding", defaults.encoding),
            auto_sync=options.get("auto_sync", True),
            sync_interval=options.get("sync_interval", 0),
            enable_locking=options.get("enable_locking", True),
            auto_reload_on_conflict=options.get("auto_reload_on_conflict", False),
            check_etag_on_read=options.get("check_etag_on_read", True),
        )

    def build_resource(
        self, *, model_name: str, options: dict[str, Any], defaults: BackendDefaults
    ) -> IResourceStore:
        prefix = options.get("prefix", "")
        model_prefix = f"{prefix}{model_name}/"
        return S3ResourceStore(
            bucket=self._bucket(options),
            access_key_id=options.get(
                "access_key_id", options.get("s3_access_key_id", "minioadmin")
            ),
            secret_access_key=options.get(
                "secret_access_key", options.get("s3_secret_access_key", "minioadmin")
            ),
            region_name=options.get(
                "region_name", options.get("s3_region", "us-east-1")
            ),
            endpoint_url=options.get("endpoint_url", options.get("s3_endpoint_url")),
            prefix=model_prefix,
            encoding=options.get("encoding", defaults.encoding),
            client_kwargs=self._client_kwargs(options),
        )

    def build_blob(
        self, *, options: dict[str, Any], defaults: BackendDefaults
    ) -> IBlobStore:
        prefix = options.get("blob_prefix", defaults.blob_prefix)
        return S3BlobStore(
            bucket=options.get("blob_bucket", self._bucket(options)),
            access_key_id=options.get(
                "access_key_id", options.get("s3_access_key_id", "minioadmin")
            ),
            secret_access_key=options.get(
                "secret_access_key", options.get("s3_secret_access_key", "minioadmin")
            ),
            region_name=options.get(
                "region_name", options.get("s3_region", "us-east-1")
            ),
            endpoint_url=options.get("endpoint_url", options.get("s3_endpoint_url")),
            prefix=prefix,
            upload_method=options.get("upload_method", defaults.upload_method),
            presigned_url_expiry=options.get(
                "presigned_url_expiry", defaults.presigned_url_expiry
            ),
            client_kwargs=self._client_kwargs(options),
        )


class SimpleMQBackendProvider(BackendProvider):
    type = "simple"
    capabilities = frozenset({"mq"})

    def build_mq_factory(
        self, *, options: dict[str, Any], defaults: BackendDefaults
    ) -> IMessageQueueFactory:
        return SimpleMessageQueueFactory(max_retries=options.get("max_retries", 3))


class RabbitMQBackendProvider(BackendProvider):
    type = "rabbitmq"
    capabilities = frozenset({"mq"})

    def build_mq_factory(
        self, *, options: dict[str, Any], defaults: BackendDefaults
    ) -> IMessageQueueFactory:
        return RabbitMQMessageQueueFactory(
            amqp_url=options.get("amqp_url", "amqp://guest:guest@localhost:5672/"),
            queue_prefix=options.get("queue_prefix", "specstar:"),
            max_retries=options.get("max_retries", 3),
            retry_delay_seconds=options.get("retry_delay_seconds", 10),
            amqp_heartbeat_seconds=options.get("amqp_heartbeat_seconds", 600),
        )  # ty:ignore[invalid-return-type]


_registry = BackendRegistry()
for _provider in (
    MemoryBackendProvider(),
    DiskBackendProvider(),
    PostgresBackendProvider(),
    S3BackendProvider(),
    SimpleMQBackendProvider(),
    RabbitMQBackendProvider(),
):
    _registry.register(_provider)


def get_backend_registry() -> BackendRegistry:
    return _registry


def register_backend_provider(provider: BackendProvider) -> None:
    """Register a custom backend provider for use in unified backend config."""

    _registry.register(provider)


def build_backend_bundle(
    backend: BackendConfig | Mapping[str, Any] | str | Path | None = None,
    *,
    storage_factory: IStorageFactory | None = None,
    message_queue_factory: IMessageQueueFactory | None = None,
) -> BackendBundle:
    """Resolve unified backend config or legacy values into runtime objects."""

    if backend is not None:
        config = BackendConfig.from_value(backend)
        registry = get_backend_registry()
        _validate_backend_config(config, registry)
        resolved_storage_factory = BackendStorageFactory(
            config=config, registry=registry
        )
        resolved_blob_store = _resolve_blob_store(config, registry)
        resolved_mq_factory = _resolve_mq_factory(config, registry)
        return BackendBundle(
            config=config,
            storage_factory=resolved_storage_factory,
            blob_store=resolved_blob_store,
            message_queue_factory=resolved_mq_factory,
        )

    resolved_storage_factory = storage_factory or MemoryStorageFactory()
    if isinstance(resolved_storage_factory, DiskStorageFactory):
        resolved_blob_store = DiskBlobStore(resolved_storage_factory.rootdir / "_blobs")
    else:
        resolved_blob_store = (
            resolved_storage_factory.build_blob_store() or MemoryBlobStore()
        )

    return BackendBundle(
        config=None,
        storage_factory=resolved_storage_factory,
        blob_store=resolved_blob_store,
        message_queue_factory=message_queue_factory,
    )


def _validate_backend_config(config: BackendConfig, registry: BackendRegistry) -> None:
    for role in ("meta", "resource", "blob"):
        binding = getattr(config, role)
        provider, options = _resolve_provider_and_options(
            config=config,
            registry=registry,
            role=role,
            binding=binding,
        )
        provider.validate(role=role, options=options, defaults=config.defaults)

    if config.mq is not None:
        provider, options = _resolve_provider_and_options(
            config=config,
            registry=registry,
            role="mq",
            binding=config.mq,
        )
        provider.validate(role="mq", options=options, defaults=config.defaults)


def _resolve_blob_store(config: BackendConfig, registry: BackendRegistry) -> IBlobStore:
    binding = config.blob
    provider, options = _resolve_provider_and_options(
        config=config,
        registry=registry,
        role="blob",
        binding=binding,
    )
    provider.validate(role="blob", options=options, defaults=config.defaults)
    return provider.build_blob(options=options, defaults=config.defaults)


def _resolve_mq_factory(
    config: BackendConfig,
    registry: BackendRegistry,
) -> IMessageQueueFactory | None:
    if config.mq is None:
        return None
    provider, options = _resolve_provider_and_options(
        config=config,
        registry=registry,
        role="mq",
        binding=config.mq,
    )
    provider.validate(role="mq", options=options, defaults=config.defaults)
    return provider.build_mq_factory(options=options, defaults=config.defaults)


def _resolve_store_role(
    *,
    config: BackendConfig,
    registry: BackendRegistry,
    role: Literal["meta", "resource"],
    model_name: str,
):
    binding = getattr(config, role)
    provider, options = _resolve_provider_and_options(
        config=config,
        registry=registry,
        role=role,
        binding=binding,
    )
    provider.validate(role=role, options=options, defaults=config.defaults)
    if role == "meta":
        return provider.build_meta(
            model_name=model_name,
            options=options,
            defaults=config.defaults,
        )
    return provider.build_resource(
        model_name=model_name,
        options=options,
        defaults=config.defaults,
    )


def _resolve_provider_and_options(
    *,
    config: BackendConfig,
    registry: BackendRegistry,
    role: BackendRole,
    binding: BackendBinding,
) -> tuple[BackendProvider, dict[str, Any]]:
    if binding.use:
        try:
            connection = config.connections[binding.use]
        except KeyError as exc:
            raise ValueError(f"unknown connection: {binding.use}") from exc
        if not connection.enabled:
            if binding.required:
                raise ValueError(f"connection is disabled: {binding.use}")
            raise ValueError(f"connection is disabled: {binding.use}")
        type_name = connection.type
        options = {**connection.options, **binding.options}
    elif binding.type:
        type_name = binding.type
        options = dict(binding.options)
    else:
        raise ValueError(f"backend binding for role {role} must define use or type")

    provider = registry.get(type_name)
    if role not in provider.capabilities:
        raise ValueError(f"backend type {type_name!r} does not support role {role!r}")
    return provider, options


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    return value


__all__ = [
    "BackendBinding",
    "BackendBundle",
    "BackendConfig",
    "BackendDefaults",
    "BackendProvider",
    "BackendRegistry",
    "BackendStorageFactory",
    "ConnectionProfile",
    "build_backend_bundle",
    "get_backend_registry",
    "register_backend_provider",
]
