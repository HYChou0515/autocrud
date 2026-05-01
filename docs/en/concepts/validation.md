# Validation (validator / IValidator / ValidationError)

SpecStar supports **custom validation** on write operations (create/update/patch/modify),
in addition to msgspec's own type-level validation.

## Two layers of validation

### A) Type-level validation (msgspec)
- Happens when decoding / constructing your `msgspec.Struct`
- Errors are typically `msgspec.ValidationError`

### B) Domain/business validation (SpecStar)
- Your custom rule checks (e.g. cross-field constraints, invariants)
- Should raise `specstar.types.ValidationError` (or `ValueError`, which SpecStar will wrap)

## Validator forms accepted

Depending on where you attach it, SpecStar accepts validators in these forms:

### 1) Callable
A simple function:

```python
def validate_user(u: User) -> None:
    if u.age < 0:
        raise ValueError("age must be >= 0")
```

### 2) `IValidator` implementation

```python
from specstar.types import IValidator

class PriceValidator(IValidator):
    def validate(self, data) -> None:
        if data.price < 0:
            raise ValueError("Price must be non-negative")
```

### 3) Pydantic model (bridge)

If you register a Pydantic `BaseModel` as the model type, SpecStar can use it as a validator
(by converting it and validating through Pydantic), when no validator is provided elsewhere.

## Practical example

A useful mental model is:

- let **msgspec** check whether the payload shape and field types are valid
- let **SpecStar validators** check whether the data makes sense for your business rules

For example:

```python
from msgspec import Struct

class User(Struct):
    name: str
    age: int


def validate_user(u: User) -> None:
    if u.age < 18:
        raise ValueError("user must be an adult")
```

In this example:

- `{"age": "abc"}` fails at the msgspec/type-validation layer
- `{"age": 12}` passes type validation but fails the domain validation rule

## Where to attach validators

### Attach via `add_model(...)`

```python
spec.add_model(User, validator=validate_user)
# or
spec.add_model(User, validator=PriceValidator())
```

### Attach via `Schema(...)`

```python
schema = Schema(User, "v2", validator=validate_user).step("v1", migrate)
spec.add_model(schema)
```

## Errors

### `ValidationError`

SpecStar uses `ValidationError` (a `ValueError` subclass) for domain validation failures.
This is intentionally distinct from `msgspec.ValidationError`.

Practical rule:

* in validators, raise `ValueError` with a clear message
* SpecStar will surface it as `ValidationError` (or pass through if already `ValidationError`)

## Common debugging pattern

If a write is rejected and you are not sure why, check the failure in this order:

1. did the payload fail type validation before your validator even ran?
2. did your custom validator reject a business rule?
3. is the real problem actually a uniqueness or schema-migration issue instead?

See also:

- [Constraints](/specstar/howto/constraints)
- [Troubleshooting](/specstar/howto/troubleshooting)
- [Pydantic integration](/specstar/howto/pydantic-integration)

