"""Test that importing specstar does not require optional dependencies.

Optional dependencies like psycopg2 (postgresql) and boto3 (s3) should only
be required when the user actually uses storage factories that need them.

These tests run each import in a **fresh subprocess** with a ``MetaPathFinder``
that blocks the target package. The earlier in-process approach
(``sys.modules.pop`` + ``patch("builtins.__import__")``) was flaky under
load because other tests could leave partial / cached module state that
subverted the simulated "package is missing" scenario.
"""

import subprocess
import sys

_HARNESS = """\
import sys
import importlib.abc

BLOCKED = set({blocked!r})


class _Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        top = fullname.split('.')[0]
        if top in BLOCKED:
            raise ImportError(
                f"Test-simulated missing package: {{fullname!r}}"
            )
        return None


# Prepend so we run before the standard finders, and proactively drop any
# already-loaded cached entries for the blocked packages.
sys.meta_path.insert(0, _Blocker())
for k in list(sys.modules):
    top = k.split('.')[0]
    if top in BLOCKED:
        del sys.modules[k]

{probe}
"""


def _run_isolated(blocked: list[str], probe: str) -> subprocess.CompletedProcess:
    """Run *probe* in a fresh subprocess where the *blocked* packages
    raise ImportError at import time.
    """
    script = _HARNESS.format(blocked=blocked, probe=probe)
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestOptionalImportPsycopg2:
    """psycopg2 should NOT be required by ``import specstar``."""

    def test_import_specstar_without_psycopg2(self):
        result = _run_isolated(
            blocked=["psycopg2"],
            probe=(
                "import specstar\n"
                "assert hasattr(specstar, 'SpecStar')\n"
                "assert hasattr(specstar, 'spec')\n"
                "assert hasattr(specstar, 'Schema')\n"
            ),
        )
        assert result.returncode == 0, (
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )

    def test_import_storage_factory_without_psycopg2(self):
        result = _run_isolated(
            blocked=["psycopg2"],
            probe=(
                "import specstar.resource_manager.storage_factory as m\n"
                "assert hasattr(m, 'IStorageFactory')\n"
                "assert hasattr(m, 'MemoryStorageFactory')\n"
            ),
        )
        assert result.returncode == 0, (
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )


class TestOptionalImportBoto3:
    """boto3 should NOT be required by ``import specstar``."""

    def test_import_specstar_without_boto3(self):
        result = _run_isolated(
            blocked=["boto3", "botocore"],
            probe=(
                "import specstar\n"
                "assert hasattr(specstar, 'SpecStar')\n"
                "assert hasattr(specstar, 'spec')\n"
            ),
        )
        assert result.returncode == 0, (
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        )
