# Capture the current user for audit fields

Every revision records `created_by` / `updated_by`. By default they are
`"anonymous"`, because SpecStar doesn't know who the caller is until you wire it
up. This page shows how to populate them with the real user — and one pitfall
that silently keeps them `"anonymous"`.

## Recommended: a `get_user` dependency that returns the user

The cleanest approach is a FastAPI dependency that **returns** the current user.
Pass it to the `DependencyProvider`; SpecStar uses its return value for every
write's audit fields. It can use any FastAPI features (`Header`, `Depends`, …):

```python
from fastapi import Header
from specstar import spec
from specstar.crud.route_templates.basic import DependencyProvider


async def get_current_user(authorization: str | None = Header(default=None)) -> str:
    return resolve_user(authorization) or "anonymous"


spec.configure(dependency_provider=DependencyProvider(get_user=get_current_user))
```

A real `get_user` always wins over `default_user` / per-model defaults, so
authenticated requests record the actual user.

## Alternative: a `ContextVar` (when the user is set elsewhere, e.g. middleware)

If the user is established outside the route (middleware, a shared dependency),
you can read it from a `ContextVar`:

```python
import contextvars
from fastapi import Depends, FastAPI, Header
from specstar import spec

current_user: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_user", default="anonymous"
)


# IMPORTANT: this dependency MUST be `async def`. See the pitfall below.
async def bind_current_user(authorization: str | None = Header(default=None)):
    current_user.set(resolve_user(authorization) or "anonymous")


app = FastAPI(dependencies=[Depends(bind_current_user)])
spec.configure(default_user=lambda: current_user.get())
spec.apply(app)
```

### ⚠️ Pitfall: a **sync** dependency silently records `anonymous`

FastAPI runs a plain `def` (sync) dependency in a threadpool. A `ContextVar`
set in that worker thread does **not** propagate back to the request handler, so
`current_user.get()` returns the default and `created_by` is silently
`"anonymous"`. Make the dependency `async def` (it runs in the request's own
context) and the value propagates. If you can't, prefer the `get_user`
dependency above, which returns the value directly and has no such caveat.

## Programmatic writes

For non-HTTP code, set the user via configuration or per call:

```python
spec.configure(default_user="batch-job")            # process-wide default
# or, per operation:
with mgr.using(user="batch-job", now=datetime.now(timezone.utc)):
    mgr.create(...)
```

Without any of these, non-strict writes fall back to `"anonymous"` + `now()`
(matching an unauthenticated HTTP request); set
`strict_operation_context=True` to make a missing context a hard error instead.
