"""Test that graphql module gives a clear error when strawberry is not installed."""

import importlib
import sys

import pytest


def test_graphql_import_without_strawberry():
    """When strawberry is not installed, importing graphql.py should raise
    ImportError with a clear message telling user to install autocrud[graphql].
    """
    # Save and remove strawberry from sys.modules to simulate it being missing
    saved_modules = {}
    modules_to_hide = [
        key
        for key in sys.modules
        if key == "strawberry" or key.startswith("strawberry.")
    ]
    for mod_name in modules_to_hide:
        saved_modules[mod_name] = sys.modules.pop(mod_name)

    # Also remove the cached graphql module so it gets re-imported
    graphql_mod_key = "autocrud.crud.route_templates.graphql"
    saved_graphql = sys.modules.pop(graphql_mod_key, None)

    # Install an import hook that blocks strawberry
    original_import = (
        __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__
    )

    def mock_import(name, *args, **kwargs):
        if name == "strawberry" or name.startswith("strawberry."):
            raise ModuleNotFoundError(f"No module named '{name}'")
        return original_import(name, *args, **kwargs)

    try:
        import builtins

        builtins.__import__ = mock_import

        with pytest.raises(ImportError, match="autocrud\\[graphql\\]"):
            importlib.import_module("autocrud.crud.route_templates.graphql")
    finally:
        # Restore everything
        builtins.__import__ = original_import
        sys.modules.update(saved_modules)
        if saved_graphql is not None:
            sys.modules[graphql_mod_key] = saved_graphql
        elif graphql_mod_key in sys.modules:
            del sys.modules[graphql_mod_key]
