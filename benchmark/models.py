"""Predefined benchmark models and random data generators.

Four model complexity levels are provided:

* **simple** — flat scalar fields
* **nested** — contains a sub-Struct and a list of sub-Structs
* **complex** — dict, list, optional, and nested fields
* **with_binary** — includes an optional ``Binary`` field
"""

from __future__ import annotations

import random
import string
from dataclasses import dataclass
from typing import Any, Callable

from msgspec import Struct

from autocrud.types import Binary

# ---------------------------------------------------------------------------
# Helper: random string generator
# ---------------------------------------------------------------------------

_WORDS = [
    "alpha",
    "bravo",
    "charlie",
    "delta",
    "echo",
    "foxtrot",
    "golf",
    "hotel",
    "india",
    "juliet",
    "kilo",
    "lima",
    "mike",
    "november",
    "oscar",
    "papa",
    "quebec",
    "romeo",
    "sierra",
    "tango",
]


def _rand_str(length: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase, k=length))


def _rand_word() -> str:
    return random.choice(_WORDS)


def _rand_sentence(n: int = 4) -> str:
    return " ".join(_rand_word() for _ in range(n))


# ---------------------------------------------------------------------------
# Model 1: SimpleItem
# ---------------------------------------------------------------------------


class SimpleItem(Struct):
    """Flat scalar fields only."""

    name: str
    value: int
    description: str = ""
    tags: list[str] = []


def _gen_simple(n: int) -> list[dict[str, Any]]:
    return [
        {
            "name": f"item-{i}-{_rand_str(4)}",
            "value": random.randint(1, 10000),
            "description": _rand_sentence(6),
            "tags": [_rand_word() for _ in range(random.randint(0, 5))],
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Model 2: NestedCharacter (with sub-Structs)
# ---------------------------------------------------------------------------


class Stats(Struct, frozen=True):
    """Character stat block."""

    strength: int = 10
    dexterity: int = 10
    intelligence: int = 10
    vitality: int = 10


class SkillRef(Struct, frozen=True):
    """Reference to a skill."""

    skill_name: str
    level: int = 1


class NestedCharacter(Struct):
    """Model with nested Struct and list of Structs."""

    name: str
    level: int
    hp: int
    mp: int
    stats: Stats = Stats()
    skills: list[SkillRef] = []
    description: str = ""


def _gen_nested(n: int) -> list[dict[str, Any]]:
    skill_names = [
        "fireball",
        "heal",
        "slash",
        "shield",
        "thunder",
        "stealth",
        "poison",
        "bless",
    ]
    return [
        {
            "name": f"char-{i}-{_rand_str(4)}",
            "level": random.randint(1, 100),
            "hp": random.randint(100, 9999),
            "mp": random.randint(10, 999),
            "stats": {
                "strength": random.randint(1, 99),
                "dexterity": random.randint(1, 99),
                "intelligence": random.randint(1, 99),
                "vitality": random.randint(1, 99),
            },
            "skills": [
                {
                    "skill_name": random.choice(skill_names),
                    "level": random.randint(1, 10),
                }
                for _ in range(random.randint(0, 4))
            ],
            "description": _rand_sentence(8),
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Model 3: ComplexEntity (dict, list, optional, nested)
# ---------------------------------------------------------------------------


class Inner(Struct, frozen=True):
    """Nested component."""

    key: str
    score: float = 0.0


class ComplexEntity(Struct):
    """Model with dict, list, optional, and nested fields."""

    name: str
    metadata: dict[str, str] = {}
    tags: list[str] = []
    inner: Inner = Inner(key="default")
    note: str | None = None


def _gen_complex(n: int) -> list[dict[str, Any]]:
    return [
        {
            "name": f"entity-{i}-{_rand_str(4)}",
            "metadata": {
                _rand_word(): _rand_str(6) for _ in range(random.randint(1, 5))
            },
            "tags": [_rand_word() for _ in range(random.randint(0, 6))],
            "inner": {
                "key": _rand_word(),
                "score": round(random.uniform(0, 100), 2),
            },
            "note": _rand_sentence(5) if random.random() > 0.3 else None,
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Model 4: BinaryAvatar (with Binary field)
# ---------------------------------------------------------------------------


class BinaryAvatar(Struct):
    """Model with an optional Binary field."""

    name: str
    image: Binary | None = None


def _gen_binary(n: int) -> list[dict[str, Any]]:
    return [
        {
            "name": f"avatar-{i}-{_rand_str(4)}",
            "image": (
                Binary(
                    data=random.randbytes(random.randint(1024, 65536)),
                    content_type="image/png",
                )
                if random.random() > 0.2
                else None
            ),
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Model Registry
# ---------------------------------------------------------------------------


@dataclass
class ModelInfo:
    """Associates a Struct class with its data generator and indexed fields."""

    struct_type: type[Struct]
    generate: Callable[[int], list[dict[str, Any]]]
    indexed_fields: list[str]


MODEL_REGISTRY: dict[str, ModelInfo] = {
    "simple": ModelInfo(
        struct_type=SimpleItem,
        generate=_gen_simple,
        indexed_fields=["name", "value"],
    ),
    "nested": ModelInfo(
        struct_type=NestedCharacter,
        generate=_gen_nested,
        indexed_fields=["name", "level"],
    ),
    "complex": ModelInfo(
        struct_type=ComplexEntity,
        generate=_gen_complex,
        indexed_fields=["name"],
    ),
    "with_binary": ModelInfo(
        struct_type=BinaryAvatar,
        generate=_gen_binary,
        indexed_fields=["name"],
    ),
}
