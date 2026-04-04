"""
Tests for PostgreSQL storage factories always using snake_case table names.

When model_naming is "kebab", model names like "game-event" would produce
invalid PostgreSQL table names (hyphens are not allowed in unquoted identifiers).
All PostgreSQL storage factories must convert model names to snake_case for table naming.
"""

from unittest.mock import patch

from autocrud.resource_manager.storage_factory import (
    PostgresDiskStorageFactory,
    PostgreSQLS3StorageFactory,
    PostgresStorageFactory,
)


class TestPostgresStorageFactoryKebabTableName:
    """PostgresStorageFactory must convert kebab-case model names to snake_case."""

    def test_kebab_model_name_converted_to_snake_case(self):
        with (
            patch(
                "autocrud.resource_manager.storage_factory.PostgresMetaStore"
            ) as mock_pg,
            patch(
                "autocrud.resource_manager.storage_factory.PostgresResourceStore"
            ) as mock_res,
        ):
            factory = PostgresStorageFactory(
                connection_string="postgresql://localhost/db",
                table_prefix="",
            )
            factory.build("game-event")

            # Meta store table name should use snake_case
            pg_kwargs = mock_pg.call_args[1]
            assert pg_kwargs["table_name"] == "game_event_meta"

            # Resource store table prefix should use snake_case
            res_kwargs = mock_res.call_args[1]
            assert res_kwargs["table_prefix"] == "game_event_"

    def test_kebab_model_name_with_prefix(self):
        with (
            patch(
                "autocrud.resource_manager.storage_factory.PostgresMetaStore"
            ) as mock_pg,
            patch(
                "autocrud.resource_manager.storage_factory.PostgresResourceStore"
            ) as mock_res,
        ):
            factory = PostgresStorageFactory(
                connection_string="postgresql://localhost/db",
                table_prefix="app_",
            )
            factory.build("game-event")

            pg_kwargs = mock_pg.call_args[1]
            assert pg_kwargs["table_name"] == "app_game_event_meta"

            res_kwargs = mock_res.call_args[1]
            assert res_kwargs["table_prefix"] == "app_game_event_"

    def test_snake_case_model_name_unchanged(self):
        with (
            patch(
                "autocrud.resource_manager.storage_factory.PostgresMetaStore"
            ) as mock_pg,
            patch(
                "autocrud.resource_manager.storage_factory.PostgresResourceStore"
            ) as mock_res,
        ):
            factory = PostgresStorageFactory(
                connection_string="postgresql://localhost/db",
                table_prefix="",
            )
            factory.build("game_event")

            pg_kwargs = mock_pg.call_args[1]
            assert pg_kwargs["table_name"] == "game_event_meta"

            res_kwargs = mock_res.call_args[1]
            assert res_kwargs["table_prefix"] == "game_event_"

    def test_pascal_case_model_name_converted(self):
        with (
            patch(
                "autocrud.resource_manager.storage_factory.PostgresMetaStore"
            ) as mock_pg,
            patch(
                "autocrud.resource_manager.storage_factory.PostgresResourceStore"
            ) as mock_res,
        ):
            factory = PostgresStorageFactory(
                connection_string="postgresql://localhost/db",
                table_prefix="",
            )
            factory.build("GameEvent")

            pg_kwargs = mock_pg.call_args[1]
            assert pg_kwargs["table_name"] == "game_event_meta"

            res_kwargs = mock_res.call_args[1]
            assert res_kwargs["table_prefix"] == "game_event_"


class TestPostgreSQLS3StorageFactoryKebabTableName:
    """PostgreSQLS3StorageFactory must convert kebab-case model names to snake_case."""

    def test_kebab_model_name_converted_to_snake_case(self):
        with (
            patch(
                "autocrud.resource_manager.storage_factory.PostgresMetaStore"
            ) as mock_pg,
            patch("autocrud.resource_manager.storage_factory.S3ResourceStore"),
        ):
            factory = PostgreSQLS3StorageFactory(
                connection_string="postgresql://localhost/db",
                s3_bucket="bucket",
                table_prefix="",
            )
            factory.build("game-event")

            pg_kwargs = mock_pg.call_args[1]
            assert pg_kwargs["table_name"] == "game_event_meta"

    def test_kebab_model_name_with_prefix(self):
        with (
            patch(
                "autocrud.resource_manager.storage_factory.PostgresMetaStore"
            ) as mock_pg,
            patch("autocrud.resource_manager.storage_factory.S3ResourceStore"),
        ):
            factory = PostgreSQLS3StorageFactory(
                connection_string="postgresql://localhost/db",
                s3_bucket="bucket",
                table_prefix="app_",
            )
            factory.build("game-event")

            pg_kwargs = mock_pg.call_args[1]
            assert pg_kwargs["table_name"] == "app_game_event_meta"


class TestPostgresDiskStorageFactoryKebabTableName:
    """PostgresDiskStorageFactory must convert kebab-case model names to snake_case."""

    def test_kebab_model_name_converted_to_snake_case(self):
        with (
            patch(
                "autocrud.resource_manager.storage_factory.PostgresMetaStore"
            ) as mock_pg,
            patch("autocrud.resource_manager.storage_factory.DiskResourceStore"),
        ):
            factory = PostgresDiskStorageFactory(
                connection_string="postgresql://localhost/db",
                rootdir="/tmp/test",
                table_prefix="",
            )
            factory.build("game-event")

            pg_kwargs = mock_pg.call_args[1]
            assert pg_kwargs["table_name"] == "game_event_meta"

    def test_kebab_model_name_with_prefix(self):
        with (
            patch(
                "autocrud.resource_manager.storage_factory.PostgresMetaStore"
            ) as mock_pg,
            patch("autocrud.resource_manager.storage_factory.DiskResourceStore"),
        ):
            factory = PostgresDiskStorageFactory(
                connection_string="postgresql://localhost/db",
                rootdir="/tmp/test",
                table_prefix="app_",
            )
            factory.build("game-event")

            pg_kwargs = mock_pg.call_args[1]
            assert pg_kwargs["table_name"] == "app_game_event_meta"
