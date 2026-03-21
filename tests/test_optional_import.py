"""Test that importing autocrud does not require optional dependencies.

Optional dependencies like psycopg2 (postgresql) and boto3 (s3) should only
be required when the user actually uses storage factories that need them.
"""

import builtins
import importlib
import sys
from unittest.mock import patch


def _make_import_blocker(*blocked_modules: str):
    """Return a side_effect function for builtins.__import__ that raises
    ImportError for any module whose top-level package is in *blocked_modules*,
    while delegating everything else to the real import machinery.
    """
    real_import = builtins.__import__

    def _blocker(name: str, *args, **kwargs):
        top = name.split(".")[0]
        if top in blocked_modules:
            raise ImportError(f"Test-simulated missing package: {name!r}")
        return real_import(name, *args, **kwargs)

    return _blocker


class TestOptionalImportPsycopg2:
    """psycopg2 should NOT be required by `import autocrud`."""

    def test_import_autocrud_without_psycopg2(self):
        """Importing autocrud must succeed even when psycopg2 is absent."""
        # Remove any cached psycopg2-related modules
        saved = {}
        to_remove = [
            k for k in sys.modules if k == "psycopg2" or k.startswith("psycopg2.")
        ]
        for k in to_remove:
            saved[k] = sys.modules.pop(k)

        # Also remove cached autocrud modules that may have already imported psycopg2
        autocrud_keys = [k for k in sys.modules if k.startswith("autocrud")]
        for k in autocrud_keys:
            saved[k] = sys.modules.pop(k)

        blocker = _make_import_blocker("psycopg2")

        try:
            with patch("builtins.__import__", side_effect=blocker):
                mod = importlib.import_module("autocrud")
                # Basic sanity: the public API should be available
                assert hasattr(mod, "AutoCRUD")
                assert hasattr(mod, "crud")
                assert hasattr(mod, "Schema")
        finally:
            # Restore original modules
            for k, v in saved.items():
                sys.modules[k] = v

    def test_import_storage_factory_without_psycopg2(self):
        """Importing IStorageFactory / MemoryStorageFactory must succeed
        even when psycopg2 is absent."""
        saved = {}
        to_remove = [
            k for k in sys.modules if k == "psycopg2" or k.startswith("psycopg2.")
        ]
        for k in to_remove:
            saved[k] = sys.modules.pop(k)

        autocrud_keys = [k for k in sys.modules if k.startswith("autocrud")]
        for k in autocrud_keys:
            saved[k] = sys.modules.pop(k)

        blocker = _make_import_blocker("psycopg2")

        try:
            with patch("builtins.__import__", side_effect=blocker):
                mod = importlib.import_module(
                    "autocrud.resource_manager.storage_factory"
                )
                assert hasattr(mod, "IStorageFactory")
                assert hasattr(mod, "MemoryStorageFactory")
        finally:
            for k, v in saved.items():
                sys.modules[k] = v


class TestOptionalImportBoto3:
    """boto3 should NOT be required by `import autocrud`."""

    def test_import_autocrud_without_boto3(self):
        """Importing autocrud must succeed even when boto3 is absent."""
        saved = {}
        to_remove = [
            k
            for k in sys.modules
            if k in ("boto3", "botocore") or k.startswith(("boto3.", "botocore."))
        ]
        for k in to_remove:
            saved[k] = sys.modules.pop(k)

        autocrud_keys = [k for k in sys.modules if k.startswith("autocrud")]
        for k in autocrud_keys:
            saved[k] = sys.modules.pop(k)

        blocker = _make_import_blocker("boto3", "botocore")

        try:
            with patch("builtins.__import__", side_effect=blocker):
                mod = importlib.import_module("autocrud")
                assert hasattr(mod, "AutoCRUD")
                assert hasattr(mod, "crud")
        finally:
            for k, v in saved.items():
                sys.modules[k] = v
