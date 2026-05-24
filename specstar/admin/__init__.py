"""Server-rendered, read-only admin UI (optional ``[admin-ui]`` extra).

Pure Python: FastAPI + Jinja2, no Node / pnpm / vite. Opt in with
``spec.apply(app, admin_ui="/admin")``. See :func:`build_admin_router`.
"""

from specstar.admin.ui import build_admin_router

__all__ = ["build_admin_router"]
