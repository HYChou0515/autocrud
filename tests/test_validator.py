"""Tests for the enhanced validation feature.

Tests cover:
1. Custom validator function passed to add_model / ResourceManager
2. Pydantic model as validator (auto-generates struct, uses Pydantic for validation)
3. IValidator protocol support
4. Validation error propagation through create/modify/update
5. Integration with AutoCRUD.add_model
"""

import datetime as dt
from typing import Optional

import msgspec
import pytest
from msgspec import Struct

from autocrud.resource_manager.core import ResourceManager
from autocrud.resource_manager.pydantic_converter import pydantic_to_struct
from autocrud.resource_manager.storage_factory import MemoryStorageFactory
from autocrud.types import ValidationError

# ===== Test Models =====


class Item(Struct):
    name: str
    price: int
    quantity: int = 0
    description: str = ""


# ===== Helpers =====


def make_mgr(resource_type=Item, **kwargs) -> ResourceManager:
    """Create a ResourceManager with memory storage."""
    storage = MemoryStorageFactory().build("test")
    return ResourceManager(resource_type, storage=storage, **kwargs)


# ===== 1. Custom Validator Function =====


class TestValidatorFunction:
    """Test using a callable as validator."""

    def test_validator_function_accepts_valid_data(self):
        """Validator function that passes should allow create."""

        def check_price(data: Item) -> None:
            if data.price < 0:
                raise ValueError("Price must be non-negative")

        mgr = make_mgr(validator=check_price)
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create(Item(name="Sword", price=100))
        assert info.resource_id is not None

    def test_validator_function_rejects_invalid_data(self):
        """Validator function that raises should block create."""

        def check_price(data: Item) -> None:
            if data.price < 0:
                raise ValueError("Price must be non-negative")

        mgr = make_mgr(validator=check_price)
        with mgr.meta_provide("user", dt.datetime.now()):
            with pytest.raises(ValidationError, match="Price must be non-negative"):
                mgr.create(Item(name="Bad", price=-1))

    def test_validator_rejects_on_modify(self):
        """Validator should also run on modify (draft)."""

        def check_price(data: Item) -> None:
            if data.price < 0:
                raise ValueError("Price must be non-negative")

        from autocrud.types import RevisionStatus

        mgr = make_mgr(validator=check_price)
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create(
                Item(name="Sword", price=100), status=RevisionStatus.draft
            )
            with pytest.raises(ValidationError, match="Price must be non-negative"):
                mgr.modify(info.resource_id, Item(name="Sword", price=-50))

    def test_validator_rejects_on_update(self):
        """Validator should also run on update."""

        def check_price(data: Item) -> None:
            if data.price < 0:
                raise ValueError("Price must be non-negative")

        mgr = make_mgr(validator=check_price)
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create(Item(name="Sword", price=100))
            with pytest.raises(ValidationError, match="Price must be non-negative"):
                mgr.update(info.resource_id, Item(name="Sword", price=-50))

    def test_validator_multiple_rules(self):
        """Validator can enforce multiple rules."""

        def validate_item(data: Item) -> None:
            errors = []
            if data.price < 0:
                errors.append("Price must be non-negative")
            if len(data.name) == 0:
                errors.append("Name must not be empty")
            if data.quantity < 0:
                errors.append("Quantity must be non-negative")
            if errors:
                raise ValueError("; ".join(errors))

        mgr = make_mgr(validator=validate_item)
        with mgr.meta_provide("user", dt.datetime.now()):
            with pytest.raises(ValidationError, match="Price must be non-negative"):
                mgr.create(Item(name="", price=-1, quantity=-5))

    def test_no_validator_allows_anything_valid_by_struct(self):
        """Without validator, any struct-valid data passes."""
        mgr = make_mgr()
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create(Item(name="", price=-999))
        assert info.resource_id is not None


# ===== 2. Pydantic Model as Validator =====


class TestPydanticValidator:
    """Test using a Pydantic BaseModel as validator."""

    @pytest.fixture(autouse=True)
    def setup_pydantic(self):
        """Skip if pydantic is not installed."""
        pytest.importorskip("pydantic")

    def test_pydantic_model_validates_on_create(self):
        """Pydantic model should validate data on create."""
        from pydantic import BaseModel, field_validator

        class ItemValidator(BaseModel):
            name: str
            price: int
            quantity: int = 0
            description: str = ""

            @field_validator("price")
            @classmethod
            def price_must_be_positive(cls, v):
                if v < 0:
                    raise ValueError("Price must be non-negative")
                return v

        mgr = make_mgr(validator=ItemValidator)
        with mgr.meta_provide("user", dt.datetime.now()):
            with pytest.raises(ValidationError, match="Price must be non-negative"):
                mgr.create(Item(name="Bad", price=-1))

    def test_pydantic_model_accepts_valid_data(self):
        """Pydantic model should allow valid data."""
        from pydantic import BaseModel, field_validator

        class ItemValidator(BaseModel):
            name: str
            price: int
            quantity: int = 0
            description: str = ""

            @field_validator("price")
            @classmethod
            def price_must_be_positive(cls, v):
                if v < 0:
                    raise ValueError("Price must be non-negative")
                return v

        mgr = make_mgr(validator=ItemValidator)
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create(Item(name="Sword", price=100))
        assert info.resource_id is not None

    def test_pydantic_as_model_auto_generates_struct(self):
        """When Pydantic model is passed as 'model' to add_model,
        system should auto-generate a struct and use Pydantic for validation."""
        from pydantic import BaseModel, field_validator

        from autocrud import AutoCRUD

        class ProductValidator(BaseModel):
            name: str
            price: int
            quantity: int = 0

            @field_validator("price")
            @classmethod
            def price_must_be_positive(cls, v):
                if v < 0:
                    raise ValueError("Price must be non-negative")
                return v

        app_crud = AutoCRUD()
        app_crud.configure()
        app_crud.add_model(ProductValidator)

        mgr = app_crud.resource_managers.get("product-validator")
        assert mgr is not None
        # The internal resource_type should be a msgspec Struct, not a Pydantic model
        assert issubclass(mgr.resource_type, Struct)
        # The struct should have the same fields
        assert hasattr(mgr.resource_type, "name")
        assert hasattr(mgr.resource_type, "price")
        assert hasattr(mgr.resource_type, "quantity")

        # Create valid data — should work
        struct_type = mgr.resource_type
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create(struct_type(name="Sword", price=100))
            assert info.resource_id is not None

        # Create invalid data — Pydantic should reject
        with mgr.meta_provide("user", dt.datetime.now()):
            with pytest.raises(ValidationError, match="Price must be non-negative"):
                mgr.create(struct_type(name="Bad", price=-1))

    def test_pydantic_complex_validation(self):
        """Pydantic model with complex cross-field validation."""
        from pydantic import BaseModel, model_validator

        class ItemValidator(BaseModel):
            name: str
            price: int
            quantity: int = 0
            description: str = ""

            @model_validator(mode="after")
            def check_total_value(self):
                if self.price * self.quantity > 1000000:
                    raise ValueError(
                        "Total value (price * quantity) cannot exceed 1,000,000"
                    )
                return self

        mgr = make_mgr(validator=ItemValidator)
        with mgr.meta_provide("user", dt.datetime.now()):
            with pytest.raises(ValidationError, match="Total value"):
                mgr.create(Item(name="Expensive", price=10000, quantity=200))


# ===== 3. IValidator Protocol =====


class TestIValidatorProtocol:
    """Test using IValidator interface."""

    def test_ivalidator_instance(self):
        """IValidator instance should work as validator."""
        from autocrud.types import IValidator

        class PriceValidator(IValidator):
            def validate(self, data) -> None:
                if data.price < 0:
                    raise ValueError("Price must be non-negative")

        mgr = make_mgr(validator=PriceValidator())
        with mgr.meta_provide("user", dt.datetime.now()):
            with pytest.raises(ValidationError, match="Price must be non-negative"):
                mgr.create(Item(name="Bad", price=-1))

    def test_ivalidator_with_context(self):
        """IValidator can hold state/context."""
        from autocrud.types import IValidator

        class MaxPriceValidator(IValidator):
            def __init__(self, max_price: int):
                self.max_price = max_price

            def validate(self, data) -> None:
                if data.price > self.max_price:
                    raise ValueError(f"Price must not exceed {self.max_price}")

        mgr = make_mgr(validator=MaxPriceValidator(max_price=500))
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create(Item(name="Cheap", price=100))
            assert info.resource_id is not None

            with pytest.raises(ValidationError, match="Price must not exceed 500"):
                mgr.create(Item(name="Expensive", price=1000))


# ===== 4. Integration with AutoCRUD.add_model =====


class TestAddModelValidator:
    """Test validator parameter in AutoCRUD.add_model."""

    def test_add_model_with_validator_function(self):
        from autocrud import AutoCRUD

        def check_price(data: Item) -> None:
            if data.price < 0:
                raise ValueError("Price must be non-negative")

        app_crud = AutoCRUD()
        app_crud.configure()
        app_crud.add_model(Item, validator=check_price)

        mgr = app_crud.resource_managers["item"]
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create(Item(name="Good", price=100))
            assert info.resource_id is not None

            with pytest.raises(ValidationError, match="Price must be non-negative"):
                mgr.create(Item(name="Bad", price=-1))

    def test_add_model_with_pydantic_validator(self):
        pytest.importorskip("pydantic")
        from pydantic import BaseModel, field_validator

        from autocrud import AutoCRUD

        class ItemValidator(BaseModel):
            name: str
            price: int
            quantity: int = 0
            description: str = ""

            @field_validator("price")
            @classmethod
            def price_must_be_positive(cls, v):
                if v < 0:
                    raise ValueError("Price must be non-negative")
                return v

        app_crud = AutoCRUD()
        app_crud.configure()
        app_crud.add_model(Item, validator=ItemValidator)

        mgr = app_crud.resource_managers["item"]
        with mgr.meta_provide("user", dt.datetime.now()):
            with pytest.raises(ValidationError, match="Price must be non-negative"):
                mgr.create(Item(name="Bad", price=-1))


# ===== 5. ValidationError type =====


class TestValidationError:
    """Test that ValidationError is properly defined and usable."""

    def test_validation_error_is_exception(self):
        assert issubclass(ValidationError, Exception)

    def test_validation_error_message(self):
        err = ValidationError("test error")
        assert str(err) == "test error"

    def test_validation_error_inherits_from_value_error(self):
        """ValidationError should be catchable as ValueError for convenience."""
        assert issubclass(ValidationError, ValueError)


# ===== 6. pydantic_to_struct =====


class TestPydanticToStruct:
    """Test pydantic_to_struct for all common Pydantic field types."""

    @pytest.fixture(autouse=True)
    def setup_pydantic(self):
        pytest.importorskip("pydantic")

    # --- Error case ---

    def test_rejects_non_basemodel(self):
        """Passing a non-BaseModel type should raise TypeError."""
        with pytest.raises(TypeError, match="Expected a Pydantic BaseModel"):
            pydantic_to_struct(str)

    def test_rejects_non_type(self):
        """Passing an instance (not a class) should raise TypeError."""
        from pydantic import BaseModel

        class Foo(BaseModel):
            x: int

        with pytest.raises(TypeError, match="Expected a Pydantic BaseModel"):
            pydantic_to_struct(Foo(x=1))  # instance, not type

    # --- Required fields (no default, annotation default is None) ---

    def test_required_fields(self):
        """Required fields with no default should become struct required fields."""
        from pydantic import BaseModel

        class RequiredModel(BaseModel):
            name: str
            age: int

        S = pydantic_to_struct(RequiredModel)
        # Should be able to create with positional args
        obj = S(name="Alice", age=30)
        assert obj.name == "Alice"
        assert obj.age == 30

        # Missing required field should raise
        with pytest.raises(TypeError):
            S(name="Alice")  # missing age

    # --- Optional / nullable fields (default=None) ---

    def test_optional_nullable_fields(self):
        """Optional[T] fields with default=None should have None default in struct."""
        from typing import Optional

        from pydantic import BaseModel

        class NullableModel(BaseModel):
            name: str
            nickname: Optional[str] = None
            age: int | None = None

        S = pydantic_to_struct(NullableModel)
        obj = S(name="Bob")
        assert obj.name == "Bob"
        assert obj.nickname is None
        assert obj.age is None

    # --- Fields with explicit defaults ---

    def test_fields_with_defaults(self):
        """Fields with explicit non-None defaults should preserve them."""
        from pydantic import BaseModel

        class DefaultsModel(BaseModel):
            name: str
            count: int = 0
            label: str = "default"
            active: bool = True

        S = pydantic_to_struct(DefaultsModel)
        obj = S(name="Test")
        assert obj.count == 0
        assert obj.label == "default"
        assert obj.active is True

    # --- Common scalar types ---

    def test_common_scalar_types(self):
        """Test str, int, float, bool fields."""
        from pydantic import BaseModel

        class ScalarModel(BaseModel):
            s: str
            i: int
            f: float
            b: bool

        S = pydantic_to_struct(ScalarModel)
        obj = S(s="hello", i=42, f=3.14, b=True)
        assert obj.s == "hello"
        assert obj.i == 42
        assert obj.f == 3.14
        assert obj.b is True

        # Roundtrip through msgspec
        encoded = msgspec.json.encode(obj)
        decoded = msgspec.json.decode(encoded, type=S)
        assert decoded == obj

    # --- datetime types ---

    def test_datetime_fields(self):
        """Test datetime field support."""
        from pydantic import BaseModel

        class DatetimeModel(BaseModel):
            created_at: dt.datetime
            updated_at: Optional[dt.datetime] = None

        S = pydantic_to_struct(DatetimeModel)
        now = dt.datetime.now()
        obj = S(created_at=now)
        assert obj.created_at == now
        assert obj.updated_at is None

    # --- list and dict types ---

    def test_list_and_dict_fields(self):
        """Test list[T] and dict[K,V] field support."""
        from pydantic import BaseModel

        class CollectionModel(BaseModel):
            tags: list[str] = []
            scores: dict[str, int] = {}
            items: list[int]

        S = pydantic_to_struct(CollectionModel)
        obj = S(tags=["a", "b"], scores={"x": 1}, items=[10, 20])
        assert obj.tags == ["a", "b"]
        assert obj.scores == {"x": 1}
        assert obj.items == [10, 20]

        # Default values
        obj2 = S(items=[1])
        assert obj2.tags == []
        assert obj2.scores == {}

        # Roundtrip
        encoded = msgspec.json.encode(obj)
        decoded = msgspec.json.decode(encoded, type=S)
        assert decoded == obj

    # --- Mixed required, default, and nullable ---

    def test_mixed_field_kinds(self):
        """Test struct with required, defaulted, and nullable fields together."""
        from typing import Optional

        from pydantic import BaseModel

        class MixedModel(BaseModel):
            required_str: str  # required, no default
            required_int: int  # required, no default
            optional_str: Optional[str] = None  # nullable with None default
            with_default: int = 42  # explicit default
            with_list: list[str] = []  # list default

        S = pydantic_to_struct(MixedModel)

        # All required provided
        obj = S(required_str="hi", required_int=10)
        assert obj.required_str == "hi"
        assert obj.required_int == 10
        assert obj.optional_str is None
        assert obj.with_default == 42
        assert obj.with_list == []

        # Override defaults
        obj2 = S(
            required_str="hi",
            required_int=10,
            optional_str="nick",
            with_default=99,
            with_list=["a"],
        )
        assert obj2.optional_str == "nick"
        assert obj2.with_default == 99
        assert obj2.with_list == ["a"]

    # --- Roundtrip with ResourceManager ---

    def test_struct_works_with_resource_manager(self):
        """Generated struct should work end-to-end with ResourceManager."""
        from pydantic import BaseModel

        class Product(BaseModel):
            name: str
            price: float
            in_stock: bool = True
            tags: list[str] = []

        S = pydantic_to_struct(Product)
        storage = MemoryStorageFactory().build("test")
        mgr = ResourceManager(S, storage=storage)

        data = S(name="Widget", price=9.99, tags=["sale"])
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create(data)
            got = mgr.get(info.resource_id)
        assert got.data.name == "Widget"
        assert got.data.price == 9.99
        assert got.data.in_stock is True
        assert got.data.tags == ["sale"]

    # --- Struct name preserved ---

    def test_struct_preserves_class_name(self):
        """Generated struct should have the same __name__ as the Pydantic model."""
        from pydantic import BaseModel

        class MySpecialModel(BaseModel):
            x: int

        S = pydantic_to_struct(MySpecialModel)
        assert S.__name__ == "MySpecialModel"

    # --- Nested Pydantic models ---

    def test_nested_pydantic_model(self):
        """Nested Pydantic BaseModel fields should be recursively converted to Structs."""
        from pydantic import BaseModel

        class Address(BaseModel):
            city: str
            zip_code: str

        class Person(BaseModel):
            name: str
            address: Address

        S = pydantic_to_struct(Person)

        # Should be able to construct via keyword args
        obj = S(name="Alice", address={"city": "Taipei", "zip_code": "100"})
        assert obj.name == "Alice"

        # The nested field should be a msgspec Struct (not Pydantic BaseModel)
        import msgspec

        data = {"name": "Alice", "address": {"city": "Taipei", "zip_code": "100"}}
        encoded = msgspec.json.encode(data)
        decoded = msgspec.json.decode(encoded, type=S)
        assert decoded.name == "Alice"
        assert decoded.address.city == "Taipei"
        assert decoded.address.zip_code == "100"

    def test_optional_nested_pydantic_model(self):
        """Optional nested Pydantic model fields should work."""
        from pydantic import BaseModel

        class Tag(BaseModel):
            label: str
            color: str = "blue"

        class Item(BaseModel):
            name: str
            tag: Optional[Tag] = None

        S = pydantic_to_struct(Item)

        import msgspec

        # Without nested field
        data = {"name": "Widget"}
        decoded = msgspec.json.decode(msgspec.json.encode(data), type=S)
        assert decoded.name == "Widget"
        assert decoded.tag is None

        # With nested field
        data = {"name": "Widget", "tag": {"label": "sale", "color": "red"}}
        decoded = msgspec.json.decode(msgspec.json.encode(data), type=S)
        assert decoded.name == "Widget"
        assert decoded.tag.label == "sale"
        assert decoded.tag.color == "red"

    def test_list_of_nested_pydantic_model(self):
        """list[NestedModel] fields should be recursively converted."""
        from pydantic import BaseModel

        class Skill(BaseModel):
            name: str
            level: int

        class Character(BaseModel):
            name: str
            skills: list[Skill] = []

        S = pydantic_to_struct(Character)

        import msgspec

        data = {
            "name": "Hero",
            "skills": [
                {"name": "Fireball", "level": 3},
                {"name": "Shield", "level": 1},
            ],
        }
        decoded = msgspec.json.decode(msgspec.json.encode(data), type=S)
        assert decoded.name == "Hero"
        assert len(decoded.skills) == 2
        assert decoded.skills[0].name == "Fireball"
        assert decoded.skills[0].level == 3
        assert decoded.skills[1].name == "Shield"

    def test_deeply_nested_pydantic_model(self):
        """Multi-level nesting should work recursively."""
        from pydantic import BaseModel

        class Street(BaseModel):
            name: str
            number: int

        class Address(BaseModel):
            street: Street
            city: str

        class Company(BaseModel):
            name: str
            address: Address

        S = pydantic_to_struct(Company)

        import msgspec

        data = {
            "name": "Acme",
            "address": {
                "street": {"name": "Main St", "number": 42},
                "city": "Taipei",
            },
        }
        decoded = msgspec.json.decode(msgspec.json.encode(data), type=S)
        assert decoded.name == "Acme"
        assert decoded.address.city == "Taipei"
        assert decoded.address.street.name == "Main St"
        assert decoded.address.street.number == 42

    def test_nested_model_with_resource_manager(self):
        """Nested Pydantic models should work end-to-end with ResourceManager."""
        from pydantic import BaseModel

        class Address(BaseModel):
            city: str
            zip_code: str

        class Person(BaseModel):
            name: str
            age: int
            address: Address

        S = pydantic_to_struct(Person)
        storage = MemoryStorageFactory().build("test")
        mgr = ResourceManager(S, storage=storage)

        data = S(name="Alice", age=30, address={"city": "Taipei", "zip_code": "100"})
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create(data)
            got = mgr.get(info.resource_id)
        assert got.data.name == "Alice"
        assert got.data.age == 30
        assert got.data.address.city == "Taipei"
        assert got.data.address.zip_code == "100"

    # --- Discriminated Union (Pydantic → msgspec Tagged Union) ---

    def test_discriminated_union_basic(self):
        """Pydantic discriminated union should convert to msgspec tagged union."""
        from typing import Literal

        from pydantic import BaseModel, Field

        class Cat(BaseModel):
            kind: Literal["cat"] = "cat"
            meow_volume: int = 5

        class Dog(BaseModel):
            kind: Literal["dog"] = "dog"
            bark_volume: int = 10

        class Pet(BaseModel):
            name: str
            animal: Cat | Dog = Field(discriminator="kind")

        S = pydantic_to_struct(Pet)

        import msgspec

        # Decode a cat
        data = {"name": "Whiskers", "animal": {"kind": "cat", "meow_volume": 8}}
        decoded = msgspec.json.decode(msgspec.json.encode(data), type=S)
        assert decoded.name == "Whiskers"
        assert decoded.animal.meow_volume == 8
        assert type(decoded.animal).__name__ == "Cat"

        # Decode a dog
        data = {"name": "Rex", "animal": {"kind": "dog", "bark_volume": 3}}
        decoded = msgspec.json.decode(msgspec.json.encode(data), type=S)
        assert decoded.name == "Rex"
        assert decoded.animal.bark_volume == 3
        assert type(decoded.animal).__name__ == "Dog"

    def test_discriminated_union_int_tag(self):
        """Discriminated union with int Literal tags should work."""
        from typing import Literal

        from pydantic import BaseModel, Field

        class TypeA(BaseModel):
            type_id: Literal[1] = 1
            value_a: str = ""

        class TypeB(BaseModel):
            type_id: Literal[2] = 2
            value_b: int = 0

        class Container(BaseModel):
            item: TypeA | TypeB = Field(discriminator="type_id")

        S = pydantic_to_struct(Container)

        import msgspec

        data = {"item": {"type_id": 1, "value_a": "hello"}}
        decoded = msgspec.json.decode(msgspec.json.encode(data), type=S)
        assert type(decoded.item).__name__ == "TypeA"
        assert decoded.item.value_a == "hello"

        data = {"item": {"type_id": 2, "value_b": 42}}
        decoded = msgspec.json.decode(msgspec.json.encode(data), type=S)
        assert type(decoded.item).__name__ == "TypeB"
        assert decoded.item.value_b == 42

    def test_discriminated_union_with_resource_manager(self):
        """Discriminated union should work end-to-end with ResourceManager."""
        from typing import Literal

        from pydantic import BaseModel, Field

        class Email(BaseModel):
            method: Literal["email"] = "email"
            address: str

        class SMS(BaseModel):
            method: Literal["sms"] = "sms"
            phone: str

        class Notification(BaseModel):
            title: str
            channel: Email | SMS = Field(discriminator="method")

        S = pydantic_to_struct(Notification)
        storage = MemoryStorageFactory().build("test")
        mgr = ResourceManager(S, storage=storage)

        data = S(
            title="Alert",
            channel={"method": "email", "address": "a@b.com"},
        )
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create(data)
            got = mgr.get(info.resource_id)
        assert got.data.title == "Alert"
        assert got.data.channel.address == "a@b.com"
        assert type(got.data.channel).__name__ == "Email"

    def test_discriminated_union_optional(self):
        """Optional discriminated union field should work."""
        from typing import Literal

        from pydantic import BaseModel, Field

        class Circle(BaseModel):
            shape: Literal["circle"] = "circle"
            radius: float

        class Square(BaseModel):
            shape: Literal["square"] = "square"
            side: float

        class Drawing(BaseModel):
            name: str
            main_shape: Circle | Square = Field(discriminator="shape")
            extra_shape: Circle | Square | None = Field(
                default=None, discriminator="shape"
            )

        S = pydantic_to_struct(Drawing)

        import msgspec

        # Without optional field
        data = {
            "name": "art",
            "main_shape": {"shape": "circle", "radius": 5.0},
        }
        decoded = msgspec.json.decode(msgspec.json.encode(data), type=S)
        assert decoded.extra_shape is None
        assert type(decoded.main_shape).__name__ == "Circle"

        # With optional field
        data["extra_shape"] = {"shape": "square", "side": 3.0}
        decoded = msgspec.json.decode(msgspec.json.encode(data), type=S)
        assert type(decoded.extra_shape).__name__ == "Square"
        assert decoded.extra_shape.side == 3.0

    def test_list_of_discriminated_union(self):
        """list[DiscriminatedUnion] should work."""
        from typing import Annotated, Literal

        from pydantic import BaseModel, Field

        class Add(BaseModel):
            op: Literal["add"] = "add"
            value: int

        class Mul(BaseModel):
            op: Literal["mul"] = "mul"
            factor: int

        class Pipeline(BaseModel):
            steps: list[Annotated[Add | Mul, Field(discriminator="op")]]

        S = pydantic_to_struct(Pipeline)

        import msgspec

        data = {
            "steps": [
                {"op": "add", "value": 10},
                {"op": "mul", "factor": 2},
                {"op": "add", "value": 5},
            ]
        }
        decoded = msgspec.json.decode(msgspec.json.encode(data), type=S)
        assert len(decoded.steps) == 3
        assert type(decoded.steps[0]).__name__ == "Add"
        assert decoded.steps[0].value == 10
        assert type(decoded.steps[1]).__name__ == "Mul"
        assert decoded.steps[1].factor == 2


# ===== 7. Unsupported Pydantic Features =====


class TestPydanticToStructUnsupported:
    """Test that unsupported Pydantic features raise clear errors."""

    def test_rejects_model_with_computed_field(self):
        """Pydantic computed_field is not supported — should raise or be excluded."""
        from pydantic import BaseModel, computed_field

        class WithComputed(BaseModel):
            first: str
            last: str

            @computed_field
            @property
            def full_name(self) -> str:
                return f"{self.first} {self.last}"

        # computed_field is not in model_fields, so it should be silently
        # excluded and the struct should work with only `first` and `last`.
        S = pydantic_to_struct(WithComputed)
        obj = S(first="Alice", last="Chen")
        assert obj.first == "Alice"
        assert obj.last == "Chen"
        assert not hasattr(obj, "full_name")

    def test_rejects_model_with_validator_decorator(self):
        """Pydantic @field_validator is ignored — validation is Pydantic's job,
        struct only carries data structure."""
        from pydantic import BaseModel, field_validator

        class WithValidator(BaseModel):
            age: int

            @field_validator("age")
            @classmethod
            def check_positive(cls, v: int) -> int:
                if v < 0:
                    raise ValueError("negative")
                return v

        # field_validator doesn't affect struct generation
        S = pydantic_to_struct(WithValidator)
        # Struct allows any int — validation is only enforced by Pydantic
        obj = S(age=-5)
        assert obj.age == -5

    def test_rejects_root_model(self):
        """Pydantic RootModel is not supported — should raise TypeError."""
        from pydantic import RootModel

        class Tags(RootModel[list[str]]):
            pass

        with pytest.raises(TypeError, match="RootModel is not supported"):
            pydantic_to_struct(Tags)

    def test_rejects_model_with_private_attributes(self):
        """Pydantic private attributes (_xxx) are not in model_fields,
        so they should be silently excluded from the struct."""
        from pydantic import BaseModel, PrivateAttr

        class WithPrivate(BaseModel):
            name: str
            _secret: str = PrivateAttr(default="hidden")

        S = pydantic_to_struct(WithPrivate)
        obj = S(name="Alice")
        assert obj.name == "Alice"
        assert not hasattr(obj, "_secret")

    def test_rejects_model_with_json_schema_extra(self):
        """model_config extras should not affect struct generation."""
        from pydantic import BaseModel

        class WithConfig(BaseModel):
            model_config = {"str_strip_whitespace": True, "strict": True}

            name: str
            age: int

        # Config is Pydantic-only, struct just carries the data shape
        S = pydantic_to_struct(WithConfig)
        obj = S(name="  Alice  ", age=30)
        assert obj.name == "  Alice  "  # No stripping — struct doesn't enforce

    def test_rejects_model_with_alias(self):
        """Pydantic field aliases are ignored — struct uses Python field names."""
        from pydantic import BaseModel, Field

        class WithAlias(BaseModel):
            user_name: str = Field(alias="userName")
            age: int

        S = pydantic_to_struct(WithAlias)
        obj = S(user_name="Alice", age=30)
        assert obj.user_name == "Alice"

    def test_rejects_non_serializable_types(self):
        """Fields with non-msgspec-serializable custom types should fail at
        encode/decode time, not at struct generation time."""
        from typing import Any

        from pydantic import BaseModel

        class WithAny(BaseModel):
            name: str
            payload: Any  # msgspec handles Any but can't round-trip custom objects

        # Struct generation succeeds (it doesn't validate serializability)
        S = pydantic_to_struct(WithAny)
        assert "payload" in S.__struct_fields__

        # Simple values work
        import msgspec

        obj = S(name="test", payload={"key": "val"})
        encoded = msgspec.json.encode(obj)
        decoded = msgspec.json.decode(encoded, type=S)
        assert decoded.name == "test"
        assert decoded.payload == {"key": "val"}


# ===== 8. Internal converter edge cases =====


class TestPydanticConverterEdgeCases:
    """Cover internal edge cases of _convert_annotation and _pydantic_to_struct_tagged."""

    def test_annotated_without_discriminator_plain_type(self):
        """Annotated[plain_type, some_metadata] without FieldInfo discriminator
        should pass through unchanged when the inner type needs no conversion."""
        from typing import Annotated

        from pydantic import BaseModel

        class Simple(BaseModel):
            value: Annotated[int, "some metadata"]

        S = pydantic_to_struct(Simple)
        obj = S(value=42)
        assert obj.value == 42

        # Roundtrip with msgspec
        data = {"value": 42}
        decoded = msgspec.json.decode(msgspec.json.encode(data), type=S)
        assert decoded.value == 42

    def test_annotated_without_discriminator_nested_model(self):
        """Annotated[NestedModel, some_metadata] without discriminator
        should still recursively convert the inner BaseModel."""
        from typing import Annotated

        from pydantic import BaseModel, Field

        class Inner(BaseModel):
            x: int

        class Outer(BaseModel):
            child: Annotated[Inner, Field(description="a nested model")]

        S = pydantic_to_struct(Outer)
        data = {"child": {"x": 10}}
        decoded = msgspec.json.decode(msgspec.json.encode(data), type=S)
        assert decoded.child.x == 10

    def test_annotated_nested_in_list_plain_type_unchanged(self):
        """list[Annotated[int, meta]] — inner type unchanged, should return
        the original Annotated annotation (line 137-138)."""
        from typing import Annotated

        from pydantic import BaseModel

        class M(BaseModel):
            values: list[Annotated[int, "gt0"]]

        S = pydantic_to_struct(M)
        data = {"values": [1, 2, 3]}
        decoded = msgspec.json.decode(msgspec.json.encode(data), type=S)
        assert decoded.values == [1, 2, 3]

    def test_annotated_nested_in_list_with_model_converted(self):
        """list[Annotated[BaseModel, meta]] — inner type IS a model, so
        _convert_annotation replaces it with a Struct (lines 136, 139-140)."""
        from typing import Annotated

        from pydantic import BaseModel

        class Item(BaseModel):
            name: str

        class Bag(BaseModel):
            items: list[Annotated[Item, "some tag"]]

        S = pydantic_to_struct(Bag)
        data = {"items": [{"name": "a"}, {"name": "b"}]}
        decoded = msgspec.json.decode(msgspec.json.encode(data), type=S)
        assert len(decoded.items) == 2
        assert decoded.items[0].name == "a"
        assert decoded.items[1].name == "b"

    def test_tagged_struct_missing_discriminator_field(self):
        """_pydantic_to_struct_tagged should raise TypeError when discriminator
        field is not present in the model."""
        from pydantic import BaseModel

        from autocrud.resource_manager.pydantic_converter import (
            _pydantic_to_struct_tagged,
        )

        class NoKindField(BaseModel):
            name: str

        with pytest.raises(TypeError, match="Discriminator field 'kind' not found"):
            _pydantic_to_struct_tagged(NoKindField, "kind", {})

    def test_tagged_struct_non_literal_discriminator(self):
        """_pydantic_to_struct_tagged should raise TypeError when discriminator
        field is not a Literal type."""
        from pydantic import BaseModel

        from autocrud.resource_manager.pydantic_converter import (
            _pydantic_to_struct_tagged,
        )

        class BadDiscriminator(BaseModel):
            kind: str  # str, not Literal
            value: int

        with pytest.raises(TypeError, match="must be a Literal type"):
            _pydantic_to_struct_tagged(BadDiscriminator, "kind", {})

    def test_tagged_struct_optional_field_with_none_default(self):
        """Tagged struct member with Optional field defaulting to None should work."""
        from typing import Literal

        from pydantic import BaseModel, Field

        class TypeA(BaseModel):
            kind: Literal["a"] = "a"
            name: str
            description: Optional[str] = None  # This should hit line 249

        class TypeB(BaseModel):
            kind: Literal["b"] = "b"
            value: int

        class Container(BaseModel):
            item: TypeA | TypeB = Field(discriminator="kind")

        S = pydantic_to_struct(Container)

        data = {"item": {"kind": "a", "name": "test"}}
        decoded = msgspec.json.decode(msgspec.json.encode(data), type=S)
        assert decoded.item.name == "test"
        assert decoded.item.description is None

        data = {"item": {"kind": "a", "name": "test", "description": "hello"}}
        decoded = msgspec.json.decode(msgspec.json.encode(data), type=S)
        assert decoded.item.description == "hello"

    def test_discriminated_union_with_non_basemodel_member(self):
        """_convert_discriminated_union with a non-BaseModel union member
        should fall through to _convert_annotation for that member."""
        # Simulate a union where one member is just `int` (not a BaseModel)
        # Union[int, str] has no Pydantic models, so all go through _convert_annotation
        from typing import Union

        from autocrud.resource_manager.pydantic_converter import (
            _convert_discriminated_union,
        )

        result = _convert_discriminated_union(Union[int, str], "kind", {})
        # Should return Union[int, str] unchanged since neither is a BaseModel
        assert result is Union[int, str]

    def test_discriminated_union_no_args(self):
        """_convert_discriminated_union with a non-union type (no args)
        should fall through to _convert_annotation."""
        from autocrud.resource_manager.pydantic_converter import (
            _convert_discriminated_union,
        )

        # A plain type has no union args — should delegate to _convert_annotation
        result = _convert_discriminated_union(int, "kind", {})
        assert result is int

    def test_build_validator_non_callable_raises_typeerror(self):
        """build_validator should raise TypeError for non-callable input (L99)."""
        from autocrud.resource_manager.pydantic_converter import build_validator

        with pytest.raises(TypeError, match="validator must be a callable"):
            build_validator(42)  # int is not callable, not IValidator, not BaseModel

    def test_convert_annotation_generic_no_args(self):
        """_convert_annotation with a generic type that has origin but no args
        should return the annotation unchanged (L147)."""
        import typing

        from autocrud.resource_manager.pydantic_converter import _convert_annotation

        # typing.List (unparameterized) has __origin__=list but no __args__
        result = _convert_annotation(typing.List, {})
        assert result is typing.List

    def test_pydantic_to_struct_shared_model_cache_hit(self):
        """Shared nested model should be converted only once via cache (L272)."""
        from pydantic import BaseModel

        class Shared(BaseModel):
            value: int

        class Parent(BaseModel):
            a: Shared
            b: Shared  # Second reference → cache hit in _pydantic_to_struct_recursive

        S = pydantic_to_struct(Parent)
        data = {"a": {"value": 1}, "b": {"value": 2}}
        decoded = msgspec.json.decode(msgspec.json.encode(data), type=S)
        assert decoded.a.value == 1
        assert decoded.b.value == 2
        # Both fields should use the same Struct type (from cache)
        assert type(decoded.a) is type(decoded.b)
