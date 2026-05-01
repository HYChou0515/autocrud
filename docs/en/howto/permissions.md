# Permissions

SpecStar lets you enforce access control at the resource layer.

The main entry point is a permission checker. It receives a permission context for each operation and decides whether to allow, deny, or defer the decision.

---

## Default behavior

If you do not configure a custom checker, the default experience is open and convenient for development.

For production systems, you should explicitly define a permission strategy.

---

## Option 1: Allow everything

This is the simplest setup and is useful for local experiments.

```python
from specstar import spec
from specstar.permission import AllowAll

spec.configure(permission_checker=AllowAll())
```

---

## Option 2: Root-only access

If you want a single operator account to manage everything, use `RootOnly`.

```python
from specstar import spec
from specstar.permission import RootOnly

spec.configure(permission_checker=RootOnly("admin@example.com"))
```

Only the configured root user will be allowed to perform operations.

---

## Option 3: ACL-based permissions

For per-user or per-role rules, use `ACLPermissionChecker`.

```python
import datetime as dt

from specstar import spec
from specstar.permission import (
    ACLPermission,
    ACLPermissionChecker,
    PermissionResult,
    Policy,
    ResourceAction,
)

checker = ACLPermissionChecker(policy=Policy.strict)
spec.configure(permission_checker=checker)
```

Once the checker is installed, you can create permission rules through the checker's own resource manager.

```python
with checker.resource_manager.meta_provide("root", dt.datetime.now()):
    checker.resource_manager.create(
        ACLPermission(
            subject="alice",
            object="document",
            action=ResourceAction.read | ResourceAction.read_list,
            effect=PermissionResult.allow,
        )
    )
```

This rule allows `alice` to read and list document resources.

### Important ACL fields

- `subject` — who the rule applies to
- `object` — the target resource type or `*`
- `action` — the requested action or action group
- `effect` — allow or deny
- `order` — lower values are evaluated first

### Policy modes

Common policy choices include:

- `Policy.strict` — deny wins, and missing rules default to deny
- `Policy.permissive` — allow wins, and missing rules default to allow

---

## Option 4: RBAC-based permissions

For role-based systems, use `RBACPermissionChecker`.

```python
import datetime as dt

from specstar import spec
from specstar.permission import (
    PermissionResult,
    RBACPermissionChecker,
    RBACPermissionEntry,
    ResourceAction,
    RoleMembership,
)

checker = RBACPermissionChecker()
spec.configure(permission_checker=checker)

with checker.resource_manager.meta_provide("root", dt.datetime.now()):
    checker.resource_manager.create(
        RoleMembership(subject="alice", group="editor")
    )
    checker.resource_manager.create(
        RBACPermissionEntry(
            subject="editor",
            object="document",
            action=ResourceAction.create | ResourceAction.update,
            effect=PermissionResult.allow,
        )
    )
```

In this setup:

- `alice` belongs to the `editor` role
- the `editor` role is allowed to create and update documents

---

## Using the admin shortcut

If you provide an admin user and do not supply a custom checker, SpecStar can enable an RBAC-style setup for you:

```python
spec.configure(admin="root@example.com")
```

Use this when you want a convenient starting point and plan to build out the rules afterward.

---

## What actions can be protected

Permission checks are tied to `ResourceAction` values such as:

- `create`
- `get`
- `update`
- `patch`
- `delete`
- `restore`
- `search_resources`
- grouped actions like `read`, `write`, or `owner`

Because actions are represented as flags, you can combine them with the bitwise OR operator.

---

## Practical tips

- use `AllowAll` only for demos or isolated internal tools
- use `RootOnly` for emergency admin-only systems
- use ACL when you want explicit user-level rules
- use RBAC when you want role inheritance and cleaner long-term management
- prefer a default-deny policy in production

---

## Related pages

- [Behavior reference](/specstar/reference/behavior)
- [Routes generation](/specstar/howto/routes)
- [Constraints](/specstar/howto/constraints)
