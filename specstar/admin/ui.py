"""Read-only admin UI router, server-rendered with Jinja2.

Templates are inline (a ``DictLoader``) so nothing needs to be packaged as
data files. The router renders straight from the in-process registry; jinja2
is only imported when the UI is actually mounted (the ``[admin-ui]`` extra).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Callable

import msgspec
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

if TYPE_CHECKING:
    from specstar.crud.core import SpecStar


_ADMIN_UI_MISSING = (
    "The admin UI needs Jinja2, which is not installed. Install the extra:\n"
    "    pip install 'specstar[admin-ui]'"
)


_BASE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{% block title %}SpecStar Admin{% endblock %}</title>
<style>
  body { font: 15px/1.5 system-ui, sans-serif; margin: 2rem auto; max-width: 60rem; padding: 0 1rem; }
  h1 { font-size: 1.4rem; } a { color: #0b6; text-decoration: none; } a:hover { text-decoration: underline; }
  nav { margin-bottom: 1.5rem; color: #888; } table { border-collapse: collapse; width: 100%; }
  th, td { text-align: left; padding: .4rem .6rem; border-bottom: 1px solid #eee; }
</style></head><body>
<nav><a href="{{ prefix }}">SpecStar Admin</a>{% block crumbs %}{% endblock %}</nav>
{% block body %}{% endblock %}
</body></html>"""

_INDEX = """{% extends "base" %}{% block body %}
<h1>Models</h1>
<ul>
{% for name in models %}<li><a href="{{ prefix }}/{{ name }}">{{ name }}</a></li>
{% endfor %}</ul>
{% endblock %}"""

_LIST = """{% extends "base" %}{% block crumbs %} / {{ model }}{% endblock %}{% block body %}
<h1>{{ model }}</h1>
<table><thead><tr><th>resource_id</th>{% for f in fields %}<th>{{ f }}</th>{% endfor %}</tr></thead>
<tbody>
{% for row in rows %}<tr>
  <td><a href="{{ prefix }}/{{ model }}/{{ row.resource_id }}">{{ row.resource_id }}</a></td>
  {% for f in fields %}<td>{{ row.cells[f] }}</td>{% endfor %}
</tr>{% endfor %}
</tbody></table>
{% endblock %}"""

_SECTION = """<h2>{{ heading }}</h2><table>
{% for k, v in rows.items() %}<tr><th>{{ k }}</th><td>{{ v }}</td></tr>{% endfor %}
</table>"""

_DETAIL = """{% extends "base" %}
{% block crumbs %} / <a href="{{ prefix }}/{{ model }}">{{ model }}</a> / {{ resource_id }}{% endblock %}
{% block body %}
<h1>{{ model }}</h1>
<p><code>{{ resource_id }}</code> &middot;
   <a href="{{ prefix }}/{{ model }}/{{ resource_id }}/revisions">revisions</a></p>
{% with heading="Data", rows=data %}""" + _SECTION + """{% endwith %}
{% with heading="Meta", rows=meta %}""" + _SECTION + """{% endwith %}
{% with heading="Revision info", rows=info %}""" + _SECTION + """{% endwith %}
{% endblock %}"""

_REVISIONS = """{% extends "base" %}
{% block crumbs %} / <a href="{{ prefix }}/{{ model }}">{{ model }}</a> /
   <a href="{{ prefix }}/{{ model }}/{{ resource_id }}">{{ resource_id }}</a> / revisions{% endblock %}
{% block body %}
<h1>Revisions of {{ resource_id }}</h1>
<ul>{% for rev in revisions %}<li><code>{{ rev }}</code></li>{% endfor %}</ul>
{% endblock %}"""


def _make_env():
    try:
        import jinja2
    except ImportError as e:  # pragma: no cover - exercised via the apply() guard
        raise ImportError(_ADMIN_UI_MISSING) from e
    return jinja2.Environment(
        loader=jinja2.DictLoader(
            {
                "base": _BASE,
                "index": _INDEX,
                "list": _LIST,
                "detail": _DETAIL,
                "revisions": _REVISIONS,
            }
        ),
        autoescape=True,
    )


def _display(struct) -> dict:
    """Struct → ordered {field: value} dict, dropping UNSET fields."""
    out = {}
    for f in struct.__struct_fields__:
        v = getattr(struct, f, msgspec.UNSET)
        if v is not msgspec.UNSET:
            out[f] = v
    return out


def build_admin_router(
    spec: "SpecStar", prefix: str, get_user: Callable | None = None
) -> APIRouter:
    """Build the read-only admin router mounted under ``prefix``.

    ``get_user`` is the app's user dependency: reads run as that user (via
    ``ResourceManager.using``) so the configured ``permission_checker`` applies,
    and a denial surfaces as 403 rather than leaking a 500.
    """
    from specstar.errors import PermissionDeniedError, ResourceNotFoundError

    env = _make_env()
    router = APIRouter(prefix=prefix.rstrip("/"))

    if get_user is None:

        def get_user() -> str:  # noqa: F811 - default when the app has none
            return "anonymous"

    def render(template: str, **ctx) -> HTMLResponse:
        ctx.setdefault("prefix", router.prefix)
        return HTMLResponse(env.get_template(template).render(**ctx))

    def _manager(model: str):
        rm = spec.resource_managers.get(model)
        if rm is None:
            raise HTTPException(status_code=404, detail=f"Unknown model {model!r}.")
        return rm

    @contextmanager
    def _guard(rm, user: str):
        # Read as the request user so permission_checker applies; map a denial
        # to 403 instead of letting it bubble up as a 500.
        try:
            with rm.using(user):
                yield
        except PermissionDeniedError:
            raise HTTPException(
                status_code=403, detail="Not permitted by the permission checker."
            )

    @router.get("", response_class=HTMLResponse, include_in_schema=False)
    def admin_index() -> HTMLResponse:
        return render("index", models=list(spec.resource_managers.keys()))

    @router.get("/{model}", response_class=HTMLResponse, include_in_schema=False)
    def admin_list(model: str, user: str = Depends(get_user)) -> HTMLResponse:
        rm = _manager(model)
        fields = list(rm.resource_type.__struct_fields__)
        with _guard(rm, user):
            rows = [
                {
                    "resource_id": item.meta.resource_id,
                    "cells": {f: getattr(item.data, f, "") for f in fields},
                }
                for item in rm.list_resources()
            ]
        return render("list", model=model, fields=fields, rows=rows)

    @router.get(
        "/{model}/{resource_id}", response_class=HTMLResponse, include_in_schema=False
    )
    def admin_detail(
        model: str, resource_id: str, user: str = Depends(get_user)
    ) -> HTMLResponse:
        rm = _manager(model)
        fields = list(rm.resource_type.__struct_fields__)
        with _guard(rm, user):
            try:
                meta = rm.get_meta(resource_id)
                resource = rm.get(resource_id)
            except ResourceNotFoundError:
                raise HTTPException(
                    status_code=404, detail=f"{model} {resource_id!r} not found."
                )
        return render(
            "detail",
            model=model,
            resource_id=resource_id,
            data={f: getattr(resource.data, f, "") for f in fields},
            meta=_display(meta),
            info=_display(resource.info),
        )

    @router.get(
        "/{model}/{resource_id}/revisions",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    def admin_revisions(
        model: str, resource_id: str, user: str = Depends(get_user)
    ) -> HTMLResponse:
        rm = _manager(model)
        with _guard(rm, user):
            try:
                revisions = rm.list_revisions(resource_id)
            except ResourceNotFoundError:
                raise HTTPException(
                    status_code=404, detail=f"{model} {resource_id!r} not found."
                )
        return render(
            "revisions", model=model, resource_id=resource_id, revisions=revisions
        )

    return router
