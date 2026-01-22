#!/usr/bin/env python3
"""⚔️ RPG 遊戲 API 系統 (S3 Backend) - AutoCRUD + FastAPI + S3 完整示範 🛡️

這個範例展示：
- 完整使用 S3 作為 backend 的 AutoCRUD 系統
- S3SqliteMetaStore: SQLite DB 存於 S3
- S3ResourceStore: 資源數據直接存於 S3
- S3BlobStore: 二進制數據 (如圖片) 存於 S3
- 支援 MinIO (本地 S3) 和 AWS S3
- 完整的 CRUD + 搜尋 + 版本控制功能

運行前準備 (使用 MinIO):
    # 1. 啟動 MinIO (使用 Docker)
    docker run -p 9000:9000 -p 9001:9001 \
        -e "MINIO_ROOT_USER=minioadmin" \
        -e "MINIO_ROOT_PASSWORD=minioadmin" \
        quay.io/minio/minio server /data --console-address ":9001"
    
    # 2. 運行此範例
    uv run python examples/rpg_game_s3_api.py

然後訪問：
    http://localhost:8000/docs - OpenAPI 文檔
    http://localhost:8000/character - 角色 API
    http://localhost:8000/guild - 公會 API
    http://localhost:9001 - MinIO Console (查看 S3 數據)
"""

import datetime as dt
from enum import Enum
from typing import Optional

import uvicorn
from fastapi import FastAPI
from msgspec import Struct

from autocrud import AutoCRUD
from autocrud.crud.route_templates.blob import BlobRouteTemplate
from autocrud.crud.route_templates.graphql import GraphQLRouteTemplate
from autocrud.query import QB
from autocrud.resource_manager.s3_storage_factory import S3StorageFactory
from autocrud.types import Binary


class CharacterClass(Enum):
    """職業系統"""

    WARRIOR = "⚔️ 戰士"
    MAGE = "🔮 法師"
    ARCHER = "🏹 弓箭手"
    DATA_KEEPER = "💾 數據守護者"  # AutoCRUD 特色職業


class ItemRarity(Enum):
    """裝備稀有度"""

    COMMON = "普通"
    RARE = "稀有"
    EPIC = "史詩"
    LEGENDARY = "傳奇"
    AUTOCRUD = "🚀 AutoCRUD 神器"


class Character(Struct):
    """遊戲角色"""

    name: str
    character_class: CharacterClass
    level: int = 1
    hp: int = 100
    mp: int = 50
    attack: int = 10
    defense: int = 5
    experience: int = 0
    gold: int = 100
    guild_name: Optional[str] = None
    special_ability: Optional[str] = None
    created_at: dt.datetime = dt.datetime.now()


class Guild(Struct):
    """遊戲公會"""

    name: str
    description: str
    leader: str
    member_count: int = 1
    level: int = 1
    treasury: int = 1000
    founded_at: dt.datetime = dt.datetime.now()


class Equipment(Struct):
    """遊戲裝備"""

    name: str
    rarity: ItemRarity
    character_class_req: Optional[CharacterClass] = None
    attack_bonus: int = 0
    defense_bonus: int = 0
    special_effect: Optional[str] = None
    price: int = 100
    icon: Optional[Binary] = None  # 二進制圖片數據，會存到 S3BlobStore


def get_random_image() -> bytes:
    """獲取隨機圖片 (用於裝備圖標)"""
    import httpx

    try:
        r = httpx.get("https://picsum.photos/200", follow_redirects=True, timeout=5.0)
        return r.content
    except Exception:
        # 如果無法獲取網路圖片，返回一個簡單的 1x1 PNG
        # 這是一個 1x1 透明 PNG 的 base64
        import base64

        return base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )


def create_sample_data(crud: AutoCRUD):
    """創建示範數據"""
    print("\n🎮 創建示範遊戲數據...")

    # 取得資源管理器
    guild_manager = crud.resource_managers.get("guild")
    character_manager = crud.resource_managers.get("character")
    equipment_manager = crud.resource_managers.get("equipment")

    if not all([guild_manager, character_manager, equipment_manager]):
        print("❌ 資源管理器未找到，請確保已註冊模型")
        return

    current_user = "game_admin"
    current_time = dt.datetime.now()

    # 🏰 創建公會
    guilds = [
        Guild(
            name="AutoCRUD 開發者聯盟",
            description="致力於推廣 AutoCRUD + S3 技術的頂尖公會",
            leader="架構師阿明",
            member_count=50,
            level=10,
            treasury=100000,
        ),
        Guild(
            name="S3 雲端騎士團",
            description="守護雲端數據安全的傳奇騎士",
            leader="S3 大師",
            member_count=25,
            level=8,
            treasury=50000,
        ),
        Guild(
            name="分佈式系統學院",
            description="精通分佈式存儲的學者聚集地",
            leader="分佈式專家",
            member_count=75,
            level=12,
            treasury=150000,
        ),
    ]

    with guild_manager.meta_provide(current_user, current_time):
        for guild in guilds:
            try:
                guild_manager.create(guild)
                print(f"✅ 創建公會: {guild.name} (存於 S3)")
            except Exception as e:
                print(f"❌ 公會創建失敗: {e}")

    # ⚔️ 創建角色
    characters = [
        Character(
            name="S3 大神",
            character_class=CharacterClass.DATA_KEEPER,
            level=99,
            hp=9999,
            mp=9999,
            attack=500,
            defense=300,
            experience=999999,
            gold=1000000,
            guild_name="AutoCRUD 開發者聯盟",
            special_ability="🚀 無限擴展存儲空間",
        ),
        Character(
            name="雲端法師",
            character_class=CharacterClass.MAGE,
            level=85,
            hp=2500,
            mp=5000,
            attack=200,
            defense=150,
            experience=750000,
            gold=500000,
            guild_name="S3 雲端騎士團",
            special_ability="☁️ 召喚雲端資源",
        ),
        Character(
            name="分佈式劍聖",
            character_class=CharacterClass.WARRIOR,
            level=90,
            hp=5000,
            mp=1000,
            attack=400,
            defense=250,
            experience=850000,
            gold=750000,
            guild_name="分佈式系統學院",
            special_ability="⚡ 並行處理攻擊",
        ),
        Character(
            name="備份弓箭手",
            character_class=CharacterClass.ARCHER,
            level=75,
            hp=2000,
            mp=3000,
            attack=300,
            defense=120,
            experience=600000,
            gold=400000,
            guild_name="S3 雲端騎士團",
            special_ability="🎯 版本控制箭術",
        ),
    ]

    with character_manager.meta_provide(current_user, current_time):
        for character in characters:
            try:
                character_manager.create(character)
                print(f"✅ 創建角色: {character.name} (Lv.{character.level}) - 存於 S3")
            except Exception as e:
                print(f"❌ 角色創建失敗: {e}")

    # 🗡️ 創建裝備 (帶圖片，會存到 S3BlobStore)
    print("\n📦 創建裝備 (含圖片數據)...")
    equipment_list = [
        Equipment(
            name="S3 神劍",
            rarity=ItemRarity.AUTOCRUD,
            character_class_req=CharacterClass.DATA_KEEPER,
            attack_bonus=200,
            defense_bonus=50,
            special_effect="🚀 數據永不遺失",
            price=1000000,
            icon=Binary(data=get_random_image()),
        ),
        Equipment(
            name="雲端守護盾",
            rarity=ItemRarity.LEGENDARY,
            character_class_req=CharacterClass.WARRIOR,
            attack_bonus=20,
            defense_bonus=150,
            special_effect="🛡️ 自動備份防護",
            price=500000,
            icon=Binary(data=get_random_image()),
        ),
        Equipment(
            name="分佈式魔杖",
            rarity=ItemRarity.EPIC,
            character_class_req=CharacterClass.MAGE,
            attack_bonus=100,
            defense_bonus=30,
            special_effect="✨ 並行施法",
            price=250000,
            icon=Binary(data=get_random_image()),
        ),
    ]

    with equipment_manager.meta_provide(current_user, current_time):
        for equipment in equipment_list:
            try:
                equipment_manager.create(equipment)
                icon_info = (
                    f"含圖片 ({len(equipment.icon.data)} bytes)"
                    if equipment.icon
                    else "無圖片"
                )
                print(
                    f"✅ 創建裝備: {equipment.name} [{equipment.rarity.value}] - {icon_info}"
                )
            except Exception as e:
                print(f"❌ 裝備創建失敗: {e}")


def demonstrate_s3_features(crud: AutoCRUD):
    """展示 S3 Backend 特性"""
    print("\n🔍 === S3 Backend 特性展示 ===")

    character_manager = crud.get_resource_manager(Character)
    if not character_manager:
        print("❌ 角色管理器未找到")
        return

    print("\n📊 1. 使用 QueryBuilder 搜尋 (數據來自 S3)")
    query = QB["level"].gte(80).sort("-level").limit(3)
    metas = character_manager.search_resources(query)
    print(f"   找到 {len(metas)} 個高等級角色:")
    for meta in metas:
        resource = character_manager.get(meta.resource_id)
        print(f"   - {resource.data.name}: Lv.{resource.data.level}")

    print("\n📊 2. 資料更新測試 (更新存於 S3)")
    if metas:
        first_meta = metas[0]
        resource = character_manager.get(first_meta.resource_id)
        print(f"   原始角色: {resource.data.name}, Level: {resource.data.level}")

        # 修改角色等級（升級 +1）
        with character_manager.meta_provide("game_master", dt.datetime.now()):
            modified_data = Character(
                name=resource.data.name,
                character_class=resource.data.character_class,
                level=resource.data.level + 1,
                hp=resource.data.hp,
                mp=resource.data.mp,
                attack=resource.data.attack,
                defense=resource.data.defense,
                experience=resource.data.experience,
                gold=resource.data.gold,
                guild_name=resource.data.guild_name,
                special_ability=resource.data.special_ability,
                created_at=resource.data.created_at,
            )
            character_manager.update(first_meta.resource_id, modified_data)

        # 讀取新版本
        updated = character_manager.get(first_meta.resource_id)
        print(f"   升級後: {updated.data.name}, Level: {updated.data.level}")
        print(f"   ✅ 資料已更新並同步到 S3！")

    print("\n📊 3. 二進制數據存儲 (Blob 存於 S3)")
    equipment_manager = crud.get_resource_manager(Equipment)
    if equipment_manager:
        eq_metas = equipment_manager.search_resources(QB["price"].gte(1).limit(1))
        if eq_metas:
            eq_resource = equipment_manager.get(eq_metas[0].resource_id)
            if eq_resource.data.icon:
                print(f"   裝備: {eq_resource.data.name}")
                print(f"   圖片大小: {eq_resource.data.icon.size} bytes")
                print(f"   檔案 ID: {eq_resource.data.icon.file_id}")
                print(f"   ✅ 圖片數據已存於 S3 Blob Store!")


def main():
    """主程序"""
    print("🎮 === RPG 遊戲 API 系統 (S3 Backend) === ⚔️")
    print("\n📦 S3 Backend 配置:")

    # S3 配置選項
    use_aws = input("使用 AWS S3 還是 MinIO? [aws/MINIO]: ").strip().lower()

    if use_aws == "aws":
        print("\n🌐 AWS S3 配置:")
        bucket = (
            input("  Bucket 名稱 [autocrud-rpg-game]: ").strip() or "autocrud-rpg-game"
        )
        access_key_id = input("  Access Key ID: ").strip()
        secret_access_key = input("  Secret Access Key: ").strip()
        region_name = input("  Region [us-east-1]: ").strip() or "us-east-1"

        storage_factory = S3StorageFactory(
            bucket=bucket,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            region_name=region_name,
            endpoint_url=None,  # 使用 AWS S3
            prefix="rpg-game/",
        )
        print(f"\n✅ 使用 AWS S3: {bucket} (region: {region_name})")
    else:
        print("\n🐳 MinIO 配置:")
        endpoint_url = (
            input("  MinIO Endpoint [http://localhost:9000]: ").strip()
            or "http://localhost:9000"
        )
        bucket = input("  Bucket 名稱 [test-autocrud]: ").strip() or "test-autocrud"
        access_key_id = input("  Access Key [minioadmin]: ").strip() or "minioadmin"
        secret_access_key = input("  Secret Key [minioadmin]: ").strip() or "minioadmin"

        storage_factory = S3StorageFactory(
            bucket=bucket,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            region_name="us-east-1",
            endpoint_url=endpoint_url,
            prefix="rpg-game/",
            auto_sync=True,  # 自動同步 SQLite DB 到 S3
            sync_interval=0,  # 立即同步
            enable_locking=True,  # 啟用 ETag-based 樂觀鎖定
        )
        print(f"\n✅ 使用 MinIO: {endpoint_url}")
        print(f"   Bucket: {bucket}")
        print(f"   可在 http://localhost:9001 查看 MinIO Console")

    # 創建 FastAPI 應用
    app = FastAPI(
        title="⚔️ RPG 遊戲管理系統 (S3 Backend)",
        description="""
        🎮 **完整的 RPG 遊戲管理 API (使用 S3 存儲)**
        
        功能特色：
        - ⚔️ **角色管理**: 創建、查詢、升級遊戲角色
        - 🏰 **公會系統**: 管理遊戲公會和成員
        - 🗡️ **裝備系統**: 武器裝備的完整管理
        - ☁️ **S3 Backend**: 所有數據存於 S3/MinIO
          - 📊 元數據: SQLite DB 存於 S3
          - 📦 資源數據: 直接存於 S3
          - 🖼️ 二進制數據: 存於 S3 Blob Store
        - 🚀 **AutoCRUD 驅動**: 自動生成的完整 CRUD API
        - 🔍 **強大搜尋**: QueryBuilder 查詢功能
        - 📖 **版本控制**: 追蹤所有數據變更歷史
        
        🎯 **快速開始**:
        1. 查看角色列表: `GET /character/data`
        2. 創建新角色: `POST /character`  
        3. 查看公會列表: `GET /guild/data`
        4. 瀏覽裝備: `GET /equipment/data`
        """,
        version="3.0.0-s3",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # 創建 AutoCRUD 實例 (使用 S3 Backend)
    crud = AutoCRUD(storage_factory=storage_factory)

    # 加入額外的 route templates
    crud.add_route_template(GraphQLRouteTemplate())
    crud.add_route_template(BlobRouteTemplate())

    # 註冊模型
    # 注意：indexed_fields 會建立索引以支援高效查詢
    crud.add_model(
        Character,
        indexed_fields=[
            ("level", int),
            ("name", str),
            ("gold", int),
            ("guild_name", str | None),
            ("character_class", CharacterClass),
        ],
    )
    crud.add_model(Guild)
    crud.add_model(Equipment, indexed_fields=[("price", int)])

    # 應用到 FastAPI
    crud.apply(app)
    crud.openapi(app)

    # 創建示範數據
    ans = input("\n需要創建示範數據嗎？[Y/n]: ").strip().lower()
    if ans != "n":
        create_sample_data(crud)

    # 展示 S3 特性
    ans = input("\n需要展示 S3 Backend 特性嗎？[Y/n]: ").strip().lower()
    if ans != "n":
        demonstrate_s3_features(crud)

    print("\n" + "=" * 60)
    print("🚀 === 服務器啟動成功 === 🚀")
    print("=" * 60)
    print("\n📖 API 文檔:")
    print("   OpenAPI: http://localhost:8000/docs")
    print("   ReDoc:   http://localhost:8000/redoc")
    print("\n⚔️ 資源端點:")
    print("   角色 API: http://localhost:8000/character/data")
    print("   公會 API: http://localhost:8000/guild/data")
    print("   裝備 API: http://localhost:8000/equipment/data")
    print("\n☁️ S3 存儲:")
    if storage_factory.endpoint_url:
        print(f"   MinIO Console: http://localhost:9001")
        print(f"   Bucket: {storage_factory.bucket}")
        print(f"   查看數據: rpg-game/ 資料夾")
    else:
        print(f"   AWS S3 Bucket: {storage_factory.bucket}")
        print(f"   Region: {storage_factory.region_name}")
    print("\n💡 提示:")
    print("   - 所有數據都存儲在 S3/MinIO 中")
    print("   - SQLite DB 會自動同步到 S3")
    print("   - 圖片等二進制數據存於 S3 Blob Store")
    print("   - 支援完整的版本控制和歷史追蹤")
    print("\n🎮 開始你的雲端 RPG 冒險吧！")
    print("=" * 60 + "\n")

    # 啟動服務器
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    main()
