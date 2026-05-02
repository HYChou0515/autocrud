"""Smoke tests for the declarative AST validator skeleton.

These tests anchor the validator's import path, error shape, and the
currently-implemented checks (blocked imports, blocked statements, blocked
builtin calls). The full allow-list is implemented later in Phase 1.5.
"""

from __future__ import annotations

import textwrap

import pytest

from specstar.validator import (
    BLOCKED_BUILTINS,
    BLOCKED_IMPORTS,
    BLOCKED_STATEMENTS,
    DeclarativeASTValidator,
    ValidationError,
)


def _validate(source: str) -> list[ValidationError]:
    return DeclarativeASTValidator().validate(textwrap.dedent(source))


class TestAcceptDeclarativePatterns:
    """Patterns that *must* pass even with the skeleton validator."""

    def test_empty_file(self) -> None:
        assert _validate("") == []

    def test_simple_struct_definition(self) -> None:
        source = """
            from msgspec import Struct

            class User(Struct):
                name: str
                email: str
        """
        assert _validate(source) == []

    def test_for_and_if_are_allowed(self) -> None:
        # Declarative wiring may legitimately loop or branch.
        source = """
            resources = ["User", "Order", "Product"]
            for name in resources:
                if name != "Product":
                    pass
        """
        assert _validate(source) == []

    def test_function_def_allowed(self) -> None:
        # Pure migration body is a valid declarative pattern.
        source = """
            def _migrate_v1_to_v2(v1: dict) -> dict:
                return {**v1, "email_address": v1["email"].lower()}
        """
        assert _validate(source) == []

    def test_lambda_with_operator_overloading(self) -> None:
        source = """
            check = lambda actor, res: actor.id == res.user_id
        """
        assert _validate(source) == []


class TestBlockedImports:
    """Modules whose import should be rejected."""

    @pytest.mark.parametrize("module", sorted(BLOCKED_IMPORTS))
    def test_top_level_import_blocked(self, module: str) -> None:
        errors = _validate(f"import {module}")
        assert len(errors) == 1
        assert errors[0].kind == "blocked_import"
        assert module in errors[0].message

    @pytest.mark.parametrize("module", sorted(BLOCKED_IMPORTS))
    def test_from_import_blocked(self, module: str) -> None:
        errors = _validate(f"from {module} import something")
        assert len(errors) == 1
        assert errors[0].kind == "blocked_import"

    def test_dotted_blocked_import_caught(self) -> None:
        errors = _validate("import urllib.request")
        assert len(errors) == 1
        assert errors[0].kind == "blocked_import"


class TestBlockedStatements:
    """Statement types that signal non-declarative behavior."""

    def test_try_block_rejected(self) -> None:
        source = """
            try:
                x = 1
            except Exception:
                x = 2
        """
        errors = _validate(source)
        assert any(e.node == "Try" for e in errors)

    def test_with_statement_rejected(self) -> None:
        source = """
            with open('x') as f:
                pass
        """
        errors = _validate(source)
        # ``With`` itself plus the ``open(...)`` call should both register.
        assert any(e.node == "With" for e in errors)

    def test_while_loop_rejected(self) -> None:
        source = """
            while True:
                pass
        """
        errors = _validate(source)
        assert any(e.node == "While" for e in errors)

    def test_raise_rejected(self) -> None:
        errors = _validate("raise ValueError('x')")
        assert any(e.node == "Raise" for e in errors)

    def test_async_def_rejected(self) -> None:
        source = """
            async def fetch():
                pass
        """
        errors = _validate(source)
        assert any(e.node == "AsyncFunctionDef" for e in errors)

    def test_blocked_statement_set_matches_design(self) -> None:
        names = {cls.__name__ for cls in BLOCKED_STATEMENTS}
        # Anchors the design doc §3.2 list. If you change one, change both.
        assert "Try" in names
        assert "With" in names
        assert "Raise" in names
        assert "While" in names
        assert "AsyncFunctionDef" in names
        assert "Global" in names


class TestBlockedBuiltins:
    """Direct calls to dangerous builtins."""

    @pytest.mark.parametrize("builtin", sorted(BLOCKED_BUILTINS))
    def test_direct_builtin_call_blocked(self, builtin: str) -> None:
        errors = _validate(f"{builtin}('payload')")
        assert any(e.kind == "blocked_builtin" and builtin in e.message for e in errors)


class TestErrorShape:
    """:class:`ValidationError` carries the metadata downstream code expects."""

    def test_error_has_line_and_column(self) -> None:
        source = "\n\nimport os\n"
        errors = _validate(source)
        assert errors[0].line == 3
        assert errors[0].col == 0

    def test_to_dicts_serializes_for_manifest(self) -> None:
        v = DeclarativeASTValidator()
        v.validate("import os")
        dicts = v.to_dicts()
        assert len(dicts) == 1
        assert dicts[0]["kind"] == "blocked_import"
        assert dicts[0]["node"] == "Import"
        assert "fix_hint" in dicts[0]

    def test_invalid_python_propagates_syntax_error(self) -> None:
        with pytest.raises(SyntaxError):
            _validate("def )(:")
