"""
PostgreSQL + S3 Backend Example

This example demonstrates how to use PostgreSQLStorageFactory for production-grade applications.

Architecture:
- PostgreSQL: Metadata storage with indexing and fast queries
- S3: Resource data and binary blob storage
- Suitable for: Medium to large scale applications (10K+ resources)

Requirements:
1. PostgreSQL database
2. AWS S3 or MinIO
3. Environment variables:
   - POSTGRES_DSN (e.g., "postgresql://user:pass@localhost:5432/gamedb")
   - AWS_ACCESS_KEY_ID
   - AWS_SECRET_ACCESS_KEY
   - S3_BUCKET (e.g., "my-game-data")
   - S3_REGION (default: "us-east-1")

Usage:
    uv run python examples/rpg_game_postgres_s3_api.py

    # Then visit http://localhost:8088/docs for API documentation
"""

import os
from datetime import datetime, timezone
from enum import Enum

import uvicorn
from fastapi import FastAPI
from msgspec import Struct

from autocrud.crud.core import AutoCRUD
from autocrud.resource_manager.basic import Encoding
from autocrud.resource_manager.storage_factory import PostgreSQLStorageFactory

# ============================================================================
# Configuration
# ============================================================================

POSTGRES_DSN = os.getenv(
    "POSTGRES_DSN",
    "postgresql://admin:password@localhost:5432/your_database",
)

S3_BUCKET = os.getenv("S3_BUCKET", "rpg-game-data")
S3_REGION = os.getenv("S3_REGION", "us-east-1")
S3_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "minioadmin")
S3_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin")
S3_ENDPOINT_URL = os.getenv(
    "S3_ENDPOINT_URL", "http://localhost:9000"
)  # None for AWS S3, "http://localhost:9000" for MinIO

# ============================================================================
# Domain Models
# ============================================================================


class CharacterClass(Enum):
    """Character classes in the game."""

    WARRIOR = "warrior"
    MAGE = "mage"
    RANGER = "ranger"
    PRIEST = "priest"


class ItemRarity(Enum):
    """Item rarity levels."""

    COMMON = "common"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


class Character(Struct):
    """Player character in RPG game."""

    name: str
    character_class: CharacterClass
    level: int
    hp: int
    mp: int
    experience: int
    gold: int


class Item(Struct):
    """Game item."""

    name: str
    rarity: ItemRarity
    item_type: str  # weapon, armor, potion, etc.
    value: int
    description: str


class Quest(Struct):
    """Game quest."""

    title: str
    description: str
    required_level: int
    reward_gold: int
    reward_experience: int
    is_completed: bool = False


# ============================================================================
# FastAPI Application Setup
# ============================================================================

app = FastAPI(
    title="RPG Game API (PostgreSQL + S3)",
    description="Production-grade RPG game backend using PostgreSQL for metadata and S3 for data storage",
    version="1.0.0",
)

# Initialize PostgreSQL + S3 storage factory
storage_factory = PostgreSQLStorageFactory(
    connection_string=POSTGRES_DSN,
    s3_bucket=S3_BUCKET,
    s3_region=S3_REGION,
    s3_access_key_id=S3_ACCESS_KEY_ID,
    s3_secret_access_key=S3_SECRET_ACCESS_KEY,
    s3_endpoint_url=S3_ENDPOINT_URL,
    encoding=Encoding.msgpack,
    table_prefix="rpg_",  # Tables will be: rpg_Character_meta, rpg_Item_meta, etc.
)

# Initialize AutoCRUD with PostgreSQL + S3 backend
crud = AutoCRUD(storage_factory=storage_factory)

# Register models with indexed fields for fast queries
crud.add_model(
    Character,
    indexed_fields=[
        ("level", int),
        ("gold", int),
        ("character_class", str),  # Enum will be converted to string
    ],
)

crud.add_model(
    Item,
    indexed_fields=[
        ("rarity", str),
        ("value", int),
    ],
)

crud.add_model(
    Quest,
    indexed_fields=[
        ("required_level", int),
        ("is_completed", bool),
    ],
)

# Mount AutoCRUD routes
crud.apply(app)
crud.openapi(app)


# ============================================================================
# Custom Endpoints
# ============================================================================


@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "message": "RPG Game API with PostgreSQL + S3 Backend",
        "storage": {
            "metadata": "PostgreSQL",
            "data": f"S3 ({S3_BUCKET})",
            "region": S3_REGION,
        },
        "docs": "/docs",
        "models": ["Character", "Item", "Quest"],
    }


@app.get("/stats")
async def get_stats():
    """Get database statistics."""
    # Note: In real application, you'd query PostgreSQL for actual counts
    return {
        "storage_backend": "PostgreSQL + S3",
        "models": {
            "Character": "Indexed: level, gold, character_class",
            "Item": "Indexed: rarity, value",
            "Quest": "Indexed: required_level, is_completed",
        },
    }


# ============================================================================
# Example Data Seeding
# ============================================================================


def seed_example_data():
    """Seed database with example data."""
    print("🌱 Seeding example data...")

    now = datetime.now(timezone.utc)

    # Create example characters
    characters = [
        Character("Aragorn", CharacterClass.RANGER, 20, 150, 80, 5000, 1000),
        Character("Gandalf", CharacterClass.MAGE, 50, 100, 300, 20000, 5000),
        Character("Legolas", CharacterClass.RANGER, 18, 120, 60, 4000, 800),
        Character("Gimli", CharacterClass.WARRIOR, 25, 200, 50, 8088, 1200),
    ]

    char_manager = crud.get_resource_manager(Character)
    with char_manager.meta_provide(user="system", now=now):
        for char in characters:
            try:
                char_manager.create(char)
                print(f"  ✓ Created character: {char.name}")
            except Exception as e:
                print(f"  ⚠ Character {char.name} may already exist: {e}")

    # Create example items
    items = [
        Item(
            "Excalibur",
            ItemRarity.LEGENDARY,
            "weapon",
            10000,
            "Legendary sword of kings",
        ),
        Item(
            "Health Potion",
            ItemRarity.COMMON,
            "potion",
            50,
            "Restores 50 HP",
        ),
        Item(
            "Dragon Scale Armor",
            ItemRarity.EPIC,
            "armor",
            5000,
            "Armor crafted from dragon scales",
        ),
    ]

    item_manager = crud.get_resource_manager(Item)
    with item_manager.meta_provide(user="system", now=now):
        for item in items:
            try:
                item_manager.create(item)
                print(f"  ✓ Created item: {item.name}")
            except Exception as e:
                print(f"  ⚠ Item {item.name} may already exist: {e}")

    # Create example quests
    quests = [
        Quest(
            "Defeat the Orc Chief",
            "Clear the orc camp in the northern woods",
            10,
            500,
            1000,
        ),
        Quest(
            "Rescue the Princess",
            "Save the princess from the dragon's lair",
            30,
            5000,
            10000,
        ),
    ]

    quest_manager = crud.get_resource_manager(Quest)
    with quest_manager.meta_provide(user="system", now=now):
        for quest in quests:
            try:
                quest_manager.create(quest)
                print(f"  ✓ Created quest: {quest.title}")
            except Exception as e:
                print(f"  ⚠ Quest {quest.title} may already exist: {e}")

    print("✅ Example data seeded successfully!")


# ============================================================================
# Application Entry Point
# ============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("🎮 RPG Game API - PostgreSQL + S3 Backend")
    print("=" * 80)
    print(f"📊 PostgreSQL: {POSTGRES_DSN}")
    print(f"☁️  S3 Bucket: {S3_BUCKET} (Region: {S3_REGION})")
    if S3_ENDPOINT_URL:
        print(f"🔗 S3 Endpoint: {S3_ENDPOINT_URL}")
    print("=" * 80)

    # Seed example data on startup
    seed_example_data()

    print("\n🚀 Starting FastAPI server...")
    print("📖 API Docs: http://localhost:8088/docs")
    print("🔍 Search: http://localhost:8088/Character/search")
    print("\n")

    uvicorn.run(app, host="0.0.0.0", port=8088)
