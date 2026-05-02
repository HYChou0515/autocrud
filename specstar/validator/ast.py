"""AST validator skeleton for declarative-only Python.

The full allow/block lists per design doc §3.2 are encoded as module-level
constants. The :class:`DeclarativeASTValidator` is a skeleton: it walks the
AST, recognizes a small set of obviously-bad patterns (imports of forbidden
modules, forbidden statement types), and returns structured errors.

Phase 1.5 (full validator) extends this with:

- attribute-access tracking (block ``getattr(__builtins__, ...)`` etc.)
- call-target tracking (only allow whitelisted symbols)
- per-function-body recursion for nested ``FunctionDef`` / ``Lambda``
- ``# specstar: allow`` escape hatch (Phase 1.6)

Until then this module exists to anchor the public surface (constants and the
validator class) so that downstream code (CLI ``verify``, skill prompt) can be
written against a stable import path.
"""

from __future__ import annotations

import ast
import re
from typing import Any

from msgspec import Struct

_ALLOW_PATTERN = re.compile(r"#\s*specstar:\s*allow\b", re.IGNORECASE)
"""Recognises ``# specstar: allow`` (with optional reason after) anywhere in
a source line. The match is case-insensitive and tolerates extra whitespace
around the colon. Lines that match are exempted from validation; matched
nodes still appear on the validator's :attr:`bypassed_lines` set so the
manifest can record them.

Same-line semantics only: the comment must sit on the same line as the AST
node it exempts (typically the statement's header line). Above-line
exemption is not supported in v0.11 — keeping the rule simple makes audit
diffs unambiguous.
"""

BLOCKED_IMPORTS: frozenset[str] = frozenset(
    {
        "os",
        "subprocess",
        "socket",
        "requests",
        "urllib",
        "urllib2",
        "urllib3",
        "http",
        "httpx",
        "aiohttp",
        "pathlib",
        "shutil",
        "tempfile",
        "threading",
        "multiprocessing",
        "asyncio",
        "ctypes",
    }
)
"""Top-level module names whose import is rejected outright.

Anything not in :data:`BLOCKED_IMPORTS` is **not** automatically allowed — a
later phase will add a positive allow-list (``specstar``, ``msgspec``,
``typing``, ``enum``, ``datetime``, ``decimal``).
"""

BLOCKED_BUILTINS: frozenset[str] = frozenset(
    {
        "exec",
        "eval",
        "compile",
        "open",
        "__import__",
        "input",
        "breakpoint",
        "getattr",
        "setattr",
        "delattr",
    }
)
"""Builtin call targets that bypass the AST sandbox if allowed.

``exec`` / ``eval`` / ``compile`` execute arbitrary code at runtime.
``open`` / ``input`` / ``breakpoint`` perform I/O.
``__import__`` is a dynamic-import escape.
``getattr`` / ``setattr`` / ``delattr`` enable runtime indirection that
defeats static analysis (e.g. ``getattr(obj, "system")``); declarative
wiring never needs them.
"""

SAFE_DUNDERS: frozenset[str] = frozenset({"__name__", "__doc__"})
"""Dunder attribute names that may legitimately be read in declarative code.

Any other dunder (``__class__``, ``__bases__``, ``__subclasses__``,
``__globals__``, ``__builtins__``, ``__dict__``, etc.) is rejected because
those are the canonical Python sandbox-escape vectors.
"""

BLOCKED_STATEMENTS: tuple[type[ast.AST], ...] = (
    ast.Try,
    ast.TryStar,
    ast.With,
    ast.AsyncWith,
    ast.AsyncFunctionDef,
    ast.Await,
    ast.Yield,
    ast.YieldFrom,
    ast.Global,
    ast.Nonlocal,
    ast.While,
    ast.Raise,
)
"""AST node types whose presence flags non-declarative behavior.

``Try``/``With``/``Raise`` imply error handling, which implies failures, which
implies I/O. ``While`` / ``Async*`` / ``Yield`` are control-flow patterns that
do not belong in declarative wiring code. ``Global`` / ``Nonlocal`` are
mutation patterns we never need.

``If`` and ``For`` are intentionally **not** here — declarative wiring may
loop over a list of similar resources or branch on an environment flag.
"""


def _find_allow_lines(source: str) -> frozenset[int]:
    """Scan source for ``# specstar: allow`` comments; return their 1-based line numbers."""
    return frozenset(
        i
        for i, line in enumerate(source.splitlines(), start=1)
        if _ALLOW_PATTERN.search(line)
    )


class ValidationError(Struct, frozen=True):
    """A single AST validation failure.

    Attributes:
        line: 1-based source line number where the violation was detected.
        col: 0-based column offset.
        kind: Short machine-readable category, e.g. ``"blocked_import"``.
        node: AST node class name (e.g. ``"Try"``, ``"ImportFrom"``).
        message: Human-readable description.
        fix_hint: Optional guidance for the user / skill on how to recover.
    """

    line: int
    col: int
    kind: str
    node: str
    message: str
    fix_hint: str | None = None


class DeclarativeASTValidator(ast.NodeVisitor):
    """Walks a Python AST and collects :class:`ValidationError` records.

    Skeleton implementation for Phase 1.5. Currently catches:

    - ``import``/``from`` of any module in :data:`BLOCKED_IMPORTS`
    - any statement node in :data:`BLOCKED_STATEMENTS`
    - any call to a builtin in :data:`BLOCKED_BUILTINS`

    Future extensions (later in Phase 1.5):

    - explicit allow-list for imports (currently anything not in BLOCKED is
      tentatively allowed)
    - call-target tracking via name resolution within the file
    - attribute-access guards (``__getattribute__`` tricks, dunder access)
    - escape hatch parsing (``# specstar: allow``) — Phase 1.6
    """

    def __init__(self) -> None:
        self.errors: list[ValidationError] = []
        self.bypassed_lines: set[int] = set()
        self._skip_lines: frozenset[int] = frozenset()

    # -- Public API --------------------------------------------------------

    def validate(
        self, source: str, *, filename: str = "<generated>"
    ) -> list[ValidationError]:
        """Parse and validate a Python source string.

        Returns a list of :class:`ValidationError`. Empty list means the source
        passed all currently-implemented checks (after applying the
        ``# specstar: allow`` escape hatch).

        After calling :meth:`validate`, :attr:`bypassed_lines` holds the line
        numbers where a violation **was** detected but suppressed by an
        ``# specstar: allow`` comment. Callers writing the manifest's
        ``validation`` block should record this set so reviewers can see what
        was waived.

        Raises ``SyntaxError`` if the source is not valid Python.
        """
        self.errors = []
        self.bypassed_lines = set()
        self._skip_lines = _find_allow_lines(source)
        tree = ast.parse(source, filename=filename, mode="exec")
        self.visit(tree)
        return list(self.errors)

    # -- Visitors ----------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            top = alias.name.split(".", 1)[0]
            if top in BLOCKED_IMPORTS:
                self._record(
                    node,
                    kind="blocked_import",
                    message=f"import of {alias.name!r} is not allowed in declarative Python",
                    fix_hint="Move I/O-bearing logic into a user module and reference it by string from spec.md.",
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module is not None:
            top = node.module.split(".", 1)[0]
            if top in BLOCKED_IMPORTS:
                self._record(
                    node,
                    kind="blocked_import",
                    message=f"import from {node.module!r} is not allowed in declarative Python",
                    fix_hint="Move I/O-bearing logic into a user module and reference it by string from spec.md.",
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Only catches direct ``name()`` calls; attribute-target calls handled
        # by the future allow-list pass.
        if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_BUILTINS:
            self._record(
                node,
                kind="blocked_builtin",
                message=f"call to builtin {node.func.id!r} is not allowed",
                fix_hint=f"{node.func.id!r} bypasses the declarative sandbox.",
            )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # Block dunder attribute access — the canonical sandbox-escape vector.
        # ``().__class__.__bases__[0].__subclasses__()`` is the textbook
        # example. We carve out a narrow safe-list (``__name__``, ``__doc__``)
        # for legitimate metadata reads.
        if (
            node.attr.startswith("__")
            and node.attr.endswith("__")
            and node.attr not in SAFE_DUNDERS
        ):
            self._record(
                node,
                kind="dunder_access",
                message=f"dunder attribute {node.attr!r} is not allowed",
                fix_hint=(
                    "Dunder attributes can be used to escape the declarative "
                    "sandbox. If you need this in real logic, move it to a "
                    "user module and reference it by string from spec.md."
                ),
            )
        self.generic_visit(node)

    def generic_visit(self, node: ast.AST) -> None:
        if isinstance(node, BLOCKED_STATEMENTS):
            self._record(
                node,
                kind="blocked_statement",
                message=f"{type(node).__name__} is not a declarative construct",
                fix_hint="Use (β) string-reference to user-written Python for non-declarative behavior.",
            )
        super().generic_visit(node)

    # -- Internal ----------------------------------------------------------

    def _record(
        self, node: ast.AST, *, kind: str, message: str, fix_hint: str | None = None
    ) -> None:
        line = getattr(node, "lineno", 0)
        if line in self._skip_lines:
            self.bypassed_lines.add(line)
            return
        self.errors.append(
            ValidationError(
                line=line,
                col=getattr(node, "col_offset", 0),
                kind=kind,
                node=type(node).__name__,
                message=message,
                fix_hint=fix_hint,
            )
        )

    # -- Convenience -------------------------------------------------------

    def to_dicts(self) -> list[dict[str, Any]]:
        """Serialize errors as plain dicts for inclusion in the manifest."""
        return [
            {
                "line": e.line,
                "col": e.col,
                "kind": e.kind,
                "node": e.node,
                "message": e.message,
                "fix_hint": e.fix_hint,
            }
            for e in self.errors
        ]
