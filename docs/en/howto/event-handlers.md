# Event Handlers

SpecStar provides lifecycle hooks around resource operations.

Use event handlers when you want to add audit logging, cross-resource updates, validation, notifications, or custom business rules around create, read, update, delete, and related actions.

---

## The basic idea

An event handler receives an event context object describing:

- the current phase
- the requested resource action
- the user and timestamp
- the resource name and resource ID when available
- the current payload or result data

A simple handler looks like this:

```python
from specstar.resource_manager.events import do
from specstar.types import EventContext, ResourceAction


def audit_log(context: EventContext) -> None:
    print(context.phase, context.action, context.resource_name)


event_handlers = do(audit_log).before(ResourceAction.create)
```

---

## Registering handlers

You can configure handlers globally:

```python
from specstar import spec

spec.configure(event_handlers=event_handlers)
```

Or pass them for a specific model when registering it.

---

## Available phases

### `before`

Runs before the operation is executed.

Use it for:

- early validation
- request auditing
- adjusting input data
- enforcing extra safety checks

If a `before` handler raises an exception, the operation stops.

### `after`

Runs after the operation stage is reached.

Use it when you want post-processing that should happen around the operation lifecycle.

### `on_success`

Runs only when the operation completes successfully.

Use it for:

- emitting notifications
- writing audit records
- chaining follow-up work
- updating dependent systems

### `on_failure`

Runs only when the operation raises an error.

Use it for:

- failure logging
- alerting
- compensation logic
- debugging support

---

## Chaining multiple handlers

You can define several handlers in one fluent expression:

```python
from specstar.resource_manager.events import do
from specstar.types import ResourceAction


def before_create(context):
    print("before create")


def after_create(context):
    print("after create")


def success_create(context):
    print("success create")


event_handlers = (
    do(before_create)
    .before(ResourceAction.create)
    .do(after_create)
    .after(ResourceAction.create)
    .do(success_create)
    .on_success(ResourceAction.create)
)
```

You can also attach one function to multiple actions by using the grouped action flags such as `ResourceAction.write`.

---

## Common patterns

### Audit every write

```python
from specstar.resource_manager.events import do
from specstar.types import ResourceAction


def audit(context):
    print(f"{context.user} -> {context.action} -> {context.resource_name}")


event_handlers = do(audit).on_success(ResourceAction.write)
```

### Block invalid input early

```python
from specstar.types import EventContext, ResourceAction


def validate_title(context: EventContext) -> None:
    if context.action == ResourceAction.create and not context.data.title.strip():
        raise ValueError("title must not be empty")
```

### Log failures

```python
from specstar.resource_manager.events import do
from specstar.types import ResourceAction


def log_failure(context):
    print("operation failed", context.action, context.resource_name)


event_handlers = do(log_failure).on_failure(ResourceAction.full)
```

---

## What actions are available

Event handlers can listen to actions such as:

- `create`
- `get`
- `update`
- `modify`
- `patch`
- `delete`
- `restore`
- `switch`
- `dump`
- `load`
- grouped flags like `read`, `write`, `lifecycle`, and `full`

---

## Good practices

- keep handlers small and focused
- raise clear exceptions in `before` when rejecting an operation
- prefer `on_success` for side effects that should not run on failure
- use grouped actions to reduce repetition when the same rule applies broadly
- avoid hiding core business logic in too many scattered handlers

---

## Related pages

- [Behavior reference](/specstar/reference/behavior)
- [Routes generation](/specstar/howto/routes)
- [Schema migration](/specstar/quickstart/schema-migration)
