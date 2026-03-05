# Validation (validator / IValidator / ValidationError)

AutoCRUD supports **custom validation** on write operations (create/update/patch/modify),
in addition to msgspec's own type-level validation.

## Two layers of validation

### A) Type-level validation (msgspec)
- Happens when decoding / constructing your `msgspec.Struct`
- Errors are typically `msgspec.ValidationError`

### B) Domain/business validation (AutoCRUD)
- Your custom rule checks (e.g. cross-field constraints, invariants)
- Should raise `autocrud.types.ValidationError` (or `ValueError`, which AutoCRUD will wrap)

## Validator forms accepted

Depending on where you attach it, AutoCRUD accepts validators in these forms:

### 1) Callable
A simple function:

```python
def validate_user(u: User) -> None:
    if u.age < 0:
        raise ValueError("age must be >= 0")
```

### 2) `IValidator` implementation

```python
from autocrud.types import IValidator

class PriceValidator(IValidator):
    def validate(self, data) -> None:
        if data.price < 0:
            raise ValueError("Price must be non-negative")
```

### 3) Pydantic model (bridge)

If you register a Pydantic `BaseModel` as the model type, AutoCRUD can use it as a validator
(by converting it and validating through Pydantic), when no validator is provided elsewhere.

## Where to attach validators

### Attach via `add_model(...)`

```python
crud.add_model(User, validator=validate_user)
# or
crud.add_model(User, validator=PriceValidator())
```

### Attach via `Schema(...)`

```python
schema = Schema(User, "v2", validator=validate_user).step("v1", migrate)
crud.add_model(schema)
```

## Errors

### `ValidationError`

AutoCRUD uses `ValidationError` (a `ValueError` subclass) for domain validation failures.
This is intentionally distinct from `msgspec.ValidationError`.

Practical rule:

* in validators, raise `ValueError` with a clear message
* AutoCRUD will surface it as `ValidationError` (or pass through if already `ValidationError`)

