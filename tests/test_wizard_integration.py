"""Wizard 生成程式碼整合測試

透過 Node bridge 呼叫 wizard 的 generateProject() 產生各種配置的 main.py，
利用 exec() 載入 FastAPI app 並用 TestClient 驗證 CRUD 功能。

涵蓋 4 種 StorageFactory（Memory, Disk, S3, PostgreSQL）
+ 2 個 custom 組合（FastSlow Redis+PG, CachedS3）
× 2 種 model style（Struct, Pydantic）
× msgpack encoding，以及全 12 種 field type。

外部服務需求（不 skip，連不上直接報錯）：
- PostgreSQL: localhost:5432 (user: postgres, db: autocrud_test)
- MinIO: localhost:9000 (minioadmin/minioadmin)
- Redis: localhost:6379
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
import types
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

WIZARD_DIR = Path(__file__).resolve().parent.parent / "wizard"


# ═══════════════════════════════════════════════════════════════
# Helper: field / model definition builders
# ═══════════════════════════════════════════════════════════════


def _field(
    name: str,
    typ: str,
    *,
    optional: bool = False,
    default: str = "",
    is_indexed: bool = False,
    is_display_name: bool = False,
    is_list: bool = False,
    ref=None,
    ref_revision=None,
    dict_key_type=None,
    dict_value_type=None,
    struct_name=None,
    union_members=None,
) -> dict:
    return {
        "name": name,
        "type": typ,
        "optional": optional,
        "default": default,
        "isIndexed": is_indexed,
        "isDisplayName": is_display_name,
        "isList": is_list,
        "ref": ref,
        "refRevision": ref_revision,
        "dictKeyType": dict_key_type,
        "dictValueType": dict_value_type,
        "structName": struct_name,
        "unionMembers": union_members,
    }


def _model(
    name: str,
    fields: list[dict],
    *,
    enums: list | None = None,
    sub_structs: list | None = None,
    schema_version: str = "v1",
) -> dict:
    return {
        "name": name,
        "inputMode": "form",
        "schemaVersion": schema_version,
        "fields": fields,
        "enums": enums or [],
        "subStructs": sub_structs or [],
        "rawCode": "",
        "enableValidator": False,
        "validatorCode": "",
    }


# ═══════════════════════════════════════════════════════════════
# Model definitions (Zone + Hero with all 12 field types)
# ═══════════════════════════════════════════════════════════════

ZONE_MODEL = _model(
    "Zone",
    [
        _field("name", "str", is_display_name=True, is_indexed=True),
        _field("description", "str", default='""'),
    ],
)

STATUS_ENUM = {
    "name": "Status",
    "values": [
        {"key": "active", "label": "active"},
        {"key": "inactive", "label": "inactive"},
        {"key": "retired", "label": "retired"},
    ],
}

SUB_EQUIPMENT = {
    "name": "SubEquipment",
    "fields": [
        _field("weapon", "str"),
        _field("armor", "str"),
    ],
    "tag": "",
}

ATTACK_SKILL = {
    "name": "AttackSkill",
    "fields": [
        _field("damage", "int"),
        _field("element", "str"),
    ],
    "tag": True,
}

DEFENSE_SKILL = {
    "name": "DefenseSkill",
    "fields": [
        _field("shield", "int"),
        _field("resistance", "float"),
    ],
    "tag": True,
}

HERO_MODEL = _model(
    "Hero",
    [
        # 1. str + DisplayName
        _field("name", "str", is_display_name=True, is_indexed=True),
        # 2. int
        _field("level", "int"),
        # 3. float
        _field("power", "float"),
        # 4. bool
        _field("active", "bool"),
        # 5. datetime
        _field("created", "datetime"),
        # 6. dict
        _field("metadata", "dict", dict_key_type="str", dict_value_type="str"),
        # 7. Ref → zone
        _field(
            "zone_id",
            "Ref",
            ref={"resource": "zone", "onDelete": "dangling"},
        ),
        # 8. RefRevision → zone
        _field(
            "zone_rev",
            "RefRevision",
            ref_revision={"resource": "zone"},
        ),
        # 9. Enum
        _field("status", "Enum"),
        # 10. Struct
        _field("equipment", "Struct", struct_name="SubEquipment"),
        # 11. Union
        _field(
            "skill",
            "Union",
            union_members=["AttackSkill", "DefenseSkill"],
        ),
        # 12. Binary (always Optional)
        _field("avatar", "Binary"),
        # 13. Optional str
        _field("nickname", "str", optional=True),
    ],
    enums=[STATUS_ENUM],
    sub_structs=[SUB_EQUIPMENT, ATTACK_SKILL, DEFENSE_SKILL],
)

BASE_MODELS = [ZONE_MODEL, HERO_MODEL]

# Pydantic-safe models: avoid Struct/Union/Binary fields which
# are inherently msgspec types and don't serialize via Pydantic JSON input.
HERO_MODEL_PYDANTIC = _model(
    "Hero",
    [
        # 1. str + DisplayName
        _field("name", "str", is_display_name=True, is_indexed=True),
        # 2. int
        _field("level", "int"),
        # 3. float
        _field("power", "float"),
        # 4. bool
        _field("active", "bool"),
        # 5. datetime
        _field("created", "datetime"),
        # 6. dict
        _field("metadata", "dict", dict_key_type="str", dict_value_type="str"),
        # 7. Ref → zone
        _field(
            "zone_id",
            "Ref",
            ref={"resource": "zone", "onDelete": "dangling"},
        ),
        # 8. RefRevision → zone
        _field(
            "zone_rev",
            "RefRevision",
            ref_revision={"resource": "zone"},
        ),
        # 9. Enum
        _field("status", "Enum"),
        # 10. Optional str
        _field("nickname", "str", optional=True),
    ],
    enums=[STATUS_ENUM],
)

PYDANTIC_MODELS = [ZONE_MODEL, HERO_MODEL_PYDANTIC]


# ═══════════════════════════════════════════════════════════════
# Wizard bridge: Node → Python
# ═══════════════════════════════════════════════════════════════


def generate_from_wizard(state_overrides: dict) -> dict[str, str]:
    """Call wizard bridge script, return {filename: content}."""
    result = subprocess.run(
        ["pnpm", "tsx", "scripts/generate-bridge.ts"],
        cwd=str(WIZARD_DIR),
        input=json.dumps(state_overrides),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Wizard bridge failed (rc={result.returncode}):\n{result.stderr}"
        )
    files = json.loads(result.stdout)
    return {f["filename"]: f["content"] for f in files}


# ═══════════════════════════════════════════════════════════════
# load_app: exec() generated main.py, return FastAPI app
# ═══════════════════════════════════════════════════════════════


def load_app(main_py_code: str, tmp_path: Path, config_name: str):
    """Apply string-replacement injections and exec() the generated code."""
    code = main_py_code

    # --- 1. Replace global `crud` with local AutoCRUD instance ---
    # The generated code uses `from autocrud import ..., crud, ...`
    # We replace `crud` in-place so tests don't pollute global state.
    code = re.sub(
        r"from autocrud import (.+)",
        _replace_crud_import,
        code,
        count=1,
    )
    # Insert `crud = AutoCRUD()` after the autocrud import block
    code = re.sub(
        r"(from autocrud(?:\.[\w.]+)? import [^\n]+\n)(?!crud = )",
        _insert_crud_instance,
        code,
        count=1,
    )

    # --- 2. Inject Encoding import if needed ---
    if "Encoding." in code and "import Encoding" not in code:
        code = code.replace(
            "from autocrud import ",
            "from autocrud.resource_manager.basic import Encoding\nfrom autocrud import ",
            1,
        )

    # --- 3. Storage path / connection injections ---
    hex_id = uuid.uuid4().hex[:8]
    # S3 bucket names: lowercase, hyphens only (no underscores)
    s3_unique = config_name + "-" + hex_id
    # DB/Redis prefix: underscores are fine
    db_unique = config_name.replace("-", "_") + "_" + hex_id

    # Disk
    code = re.sub(
        r'DiskStorageFactory\(rootdir="[^"]*"\)',
        f'DiskStorageFactory(rootdir="{tmp_path}")',
        code,
    )

    # S3
    code = re.sub(
        r'(S3StorageFactory\([^)]*?)bucket="[^"]*"',
        f'\\1bucket="autocrud-test-{s3_unique}"',
        code,
    )

    # PostgreSQL connection
    code = re.sub(
        r'connection_string="[^"]*"',
        'connection_string="postgresql://admin:password@localhost:5432/your_database"',
        code,
    )
    code = re.sub(
        r'table_prefix="[^"]*"',
        f'table_prefix="t_{db_unique}_"',
        code,
    )

    # S3 buckets for PostgreSQL storage
    for key in ("s3_bucket", "blob_bucket"):
        code = re.sub(
            rf'{key}="[^"]*"',
            f'{key}="autocrud-test-{s3_unique}"',
            code,
        )

    # Custom: Redis
    code = re.sub(
        r'redis_url="redis://[^"]*"',
        'redis_url="redis://localhost:6379"',
        code,
    )
    # For factory-generated f-string prefix: prefix=f"{model_name}:"
    code = code.replace(
        'prefix=f"{model_name}:"',
        f'prefix=f"{db_unique}:' + '{model_name}:"',
    )
    # For non-factory plain prefix: prefix=""
    code = re.sub(
        r'prefix=""',
        f'prefix="{db_unique}:"',
        code,
    )

    # Custom: Postgres meta store DSN
    code = re.sub(
        r'pg_dsn="postgresql://[^"]*"',
        'pg_dsn="postgresql://admin:password@localhost:5432/your_database"',
        code,
    )
    # For factory-generated f-string table: table_name=f"resource_meta_{model_name}"
    code = code.replace(
        'table_name=f"resource_meta_{model_name}"',
        f'table_name=f"meta_{db_unique}_' + '{model_name}"',
    )
    # For non-factory plain table: table_name="resource_meta"
    code = re.sub(
        r'table_name="resource_meta"',
        f'table_name="meta_{db_unique}"',
        code,
    )

    # Custom: CachedS3 resource store - update prefix for test isolation
    code = code.replace(
        'prefix=f"{model_name}/"',
        f'prefix=f"{s3_unique}/' + '{model_name}/"',
    )

    # Custom: CachedS3 resource store bucket
    code = re.sub(
        r'(CachedS3ResourceStore\([^)]*?)bucket="[^"]*"',
        f'\\1bucket="autocrud-test-{s3_unique}"',
        code,
    )

    # --- 4. Remove uvicorn.run ---
    code = re.sub(r"if __name__.*\n.*uvicorn\.run.*", "", code)
    code = re.sub(r"import uvicorn\n", "", code)

    # --- 5. exec in a proper module context ---
    # Create a real module so that msgspec / typing can resolve forward refs
    mod_name = f"_wizard_gen_{config_name}_{uuid.uuid4().hex[:6]}"
    module = types.ModuleType(mod_name)
    module.__file__ = f"<wizard:{config_name}>"
    sys.modules[mod_name] = module
    try:
        exec(compile(code, f"<wizard:{config_name}>", "exec"), module.__dict__)
    except Exception:
        # Print generated code for debugging
        for i, line in enumerate(code.splitlines(), 1):
            print(f"{i:4d} | {line}")
        raise

    app = getattr(module, "app", None)
    if app is None:
        raise RuntimeError(f"Generated code did not define 'app'.\nCode:\n{code}")
    # Attach module reference so caller can clean up if needed
    app._wizard_module_name = mod_name
    return app


def _replace_crud_import(match: re.Match) -> str:
    """Remove `crud` from the autocrud import line, add AutoCRUD instead."""
    imports_str = match.group(1)
    items = [i.strip() for i in imports_str.split(",")]
    items = [i for i in items if i != "crud"]
    if "AutoCRUD" not in items:
        items.append("AutoCRUD")
    return f"from autocrud import {', '.join(items)}"


def _insert_crud_instance(match: re.Match) -> str:
    """Insert `crud = AutoCRUD()` after the last autocrud import line."""
    return match.group(0) + "crud = AutoCRUD()\n"


# ═══════════════════════════════════════════════════════════════
# Configuration matrix
# ═══════════════════════════════════════════════════════════════


def _make_overrides(
    storage: str = "memory",
    model_style: str = "struct",
    encoding: str = "json",
    storage_config: dict | None = None,
    enable_graphql: bool = False,
    enable_cors: bool = False,
) -> dict:
    models = PYDANTIC_MODELS if model_style == "pydantic" else BASE_MODELS
    return {
        "storage": storage,
        "modelStyle": model_style,
        "encoding": encoding,
        "storageConfig": storage_config or {},
        "enableGraphql": enable_graphql,
        "enableCORS": enable_cors,
        "models": models,
    }


# (config_name, state_overrides, required_services)
WIZARD_CONFIGS: list[tuple[str, dict, set[str]]] = [
    # ── Memory ──
    (
        "memory-struct",
        _make_overrides(),
        set(),
    ),
    (
        "memory-pydantic",
        _make_overrides(model_style="pydantic"),
        set(),
    ),
    (
        "memory-msgpack",
        _make_overrides(encoding="msgpack"),
        set(),
    ),
    # ── Disk ──
    (
        "disk-struct",
        _make_overrides(storage="disk", storage_config={"rootdir": "./data"}),
        set(),
    ),
    (
        "disk-pydantic",
        _make_overrides(
            storage="disk",
            model_style="pydantic",
            storage_config={"rootdir": "./data"},
        ),
        set(),
    ),
    # ── S3 ──
    (
        "s3-struct",
        _make_overrides(
            storage="s3",
            storage_config={
                "bucket": "autocrud-test",
                "endpointUrl": "http://localhost:9000",
                "accessKeyId": "minioadmin",
                "secretAccessKey": "minioadmin",
                "regionName": "us-east-1",
            },
        ),
        {"minio"},
    ),
    (
        "s3-pydantic",
        _make_overrides(
            storage="s3",
            model_style="pydantic",
            storage_config={
                "bucket": "autocrud-test",
                "endpointUrl": "http://localhost:9000",
                "accessKeyId": "minioadmin",
                "secretAccessKey": "minioadmin",
                "regionName": "us-east-1",
            },
        ),
        {"minio"},
    ),
    # ── PostgreSQL ──
    (
        "postgresql-struct",
        _make_overrides(
            storage="postgresql",
            encoding="msgpack",
            storage_config={
                "connectionString": "postgresql://postgres@localhost:5432/autocrud_test",
                "s3Bucket": "autocrud-test",
                "s3EndpointUrl": "http://localhost:9000",
                "s3Region": "us-east-1",
                "s3AccessKeyId": "minioadmin",
                "s3SecretAccessKey": "minioadmin",
                "tablePrefix": "",
                "blobPrefix": "blobs/",
                "blobBucket": "autocrud-test",
            },
        ),
        {"postgresql", "minio"},
    ),
    (
        "postgresql-pydantic",
        _make_overrides(
            storage="postgresql",
            model_style="pydantic",
            encoding="msgpack",
            storage_config={
                "connectionString": "postgresql://postgres@localhost:5432/autocrud_test",
                "s3Bucket": "autocrud-test",
                "s3EndpointUrl": "http://localhost:9000",
                "s3Region": "us-east-1",
                "s3AccessKeyId": "minioadmin",
                "s3SecretAccessKey": "minioadmin",
                "tablePrefix": "",
                "blobPrefix": "blobs/",
                "blobBucket": "autocrud-test",
            },
        ),
        {"postgresql", "minio"},
    ),
    # ── Custom: FastSlow (Redis+PG meta + memory resource) ──
    (
        "custom-fastslow",
        _make_overrides(
            storage="custom",
            encoding="msgpack",
            storage_config={
                "customMetaStore": "fast-slow",
                "customResourceStore": "memory",
                "metaFastStore": "redis",
                "metaSlowStore": "postgres",
                "metaSyncInterval": 1,
                "metaRedisUrl": "redis://localhost:6379",
                "metaRedisPrefix": "",
                "metaPostgresDsn": "postgresql://admin:password@localhost:5432/your_database",
                "metaPostgresTable": "resource_meta",
            },
        ),
        {"redis", "postgresql"},
    ),
    # ── Custom: CachedS3 (memory meta + cached-s3 resource) ──
    (
        "custom-cached-s3",
        _make_overrides(
            storage="custom",
            storage_config={
                "customMetaStore": "memory",
                "customResourceStore": "cached-s3",
                "resBucket": "autocrud-test",
                "resPrefix": "",
                "resEndpointUrl": "http://localhost:9000",
                "resAccessKeyId": "minioadmin",
                "resSecretAccessKey": "minioadmin",
                "resRegionName": "us-east-1",
            },
        ),
        {"minio"},
    ),
]


# ═══════════════════════════════════════════════════════════════
# Payloads
# ═══════════════════════════════════════════════════════════════

ZONE_PAYLOAD = {"name": "Dark Forest", "description": "A mysterious forest"}

AVATAR_BYTES = b"FAKE_PNG_CONTENT_FOR_TESTING"
AVATAR_B64 = base64.b64encode(AVATAR_BYTES).decode()


def hero_payload(
    zone_resource_id: str,
    zone_revision_id: str,
    *,
    with_optional: bool = True,
    is_pydantic: bool = False,
) -> dict:
    """Build a Hero create payload with all supported field types."""
    payload: dict = {
        "name": "Aragorn",
        "level": 42,
        "power": 9001.5,
        "active": True,
        "created": "2025-01-15T10:30:00",
        "metadata": {"class": "ranger", "origin": "gondor"},
        "zone_id": zone_resource_id,
        "zone_rev": zone_revision_id,
        "status": "active",
    }
    # Struct-only fields (Struct/Union/Binary not supported in Pydantic JSON input)
    if not is_pydantic:
        payload["equipment"] = {"weapon": "Andúril", "armor": "Mithril"}
        payload["skill"] = {"type": "AttackSkill", "damage": 150, "element": "fire"}
        payload["avatar"] = {"data": AVATAR_B64}
    if with_optional:
        payload["nickname"] = "Strider"
    return payload


# ═══════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "config_name,overrides,needs",
    WIZARD_CONFIGS,
    ids=[c[0] for c in WIZARD_CONFIGS],
)
def test_wizard_crud(config_name: str, overrides: dict, needs: set, tmp_path: Path):
    """Complete CRUD integration test for a wizard-generated configuration."""
    is_pydantic = overrides.get("modelStyle") == "pydantic"

    # ── Generate code ────────────────────────────────────────
    files = generate_from_wizard(overrides)
    assert "main.py" in files, f"Wizard did not generate main.py for {config_name}"

    app = load_app(files["main.py"], tmp_path, config_name)
    client = TestClient(app)

    # ── 1. Create Zone (Ref target) ──────────────────────────
    resp = client.post("/zone", json=ZONE_PAYLOAD)
    assert resp.status_code == 200, (
        f"[{config_name}] create zone failed: {resp.status_code} {resp.text}"
    )
    zone_info = resp.json()
    zone_rid = zone_info["resource_id"]
    zone_rev = zone_info["revision_id"]
    assert zone_rid.startswith("zone:")

    # ── 2. Create Hero ───────────────────────────────────────
    payload = hero_payload(
        zone_rid, zone_rev, with_optional=True, is_pydantic=is_pydantic
    )
    resp = client.post("/hero", json=payload)
    assert resp.status_code == 200, (
        f"[{config_name}] create hero failed: {resp.status_code} {resp.text}"
    )
    hero_info = resp.json()
    hero_rid = hero_info["resource_id"]
    hero_rev = hero_info["revision_id"]
    assert hero_rid.startswith("hero:")

    # ── 3. Read Hero data ────────────────────────────────────
    resp = client.get(f"/hero/{hero_rid}/data")
    assert resp.status_code == 200, (
        f"[{config_name}] read hero failed: {resp.status_code} {resp.text}"
    )
    data = resp.json()

    # Common fields
    assert data["name"] == "Aragorn"
    assert data["level"] == 42
    assert data["power"] == 9001.5
    assert data["active"] is True
    assert "2025-01-15" in data["created"]
    assert data["metadata"] == {"class": "ranger", "origin": "gondor"}
    assert data["zone_id"] == zone_rid
    assert data["zone_rev"] == zone_rev
    assert data["status"] == "active"
    assert data["nickname"] == "Strider"

    # Struct-specific fields (not in pydantic models)
    if not is_pydantic:
        assert data["equipment"]["weapon"] == "Andúril"
        assert data["equipment"]["armor"] == "Mithril"
        assert data["skill"]["damage"] == 150
        assert data["skill"]["element"] == "fire"
        # Binary → after processing, should have file_id and size, no data
        assert "file_id" in data["avatar"]
        assert data["avatar"]["size"] == len(AVATAR_BYTES)

    # ── 4. Read Hero full ────────────────────────────────────
    resp = client.get(f"/hero/{hero_rid}/full")
    assert resp.status_code == 200
    full = resp.json()
    assert "data" in full
    assert "revision_info" in full
    assert "meta" in full
    assert full["revision_info"]["revision_id"] == hero_rev

    # ── 5. List Heroes ───────────────────────────────────────
    resp = client.get("/hero/data?limit=10")
    assert resp.status_code == 200, (
        f"[{config_name}] list heroes failed: {resp.status_code} {resp.text}"
    )
    items = resp.json()
    assert isinstance(items, list)
    assert len(items) >= 1
    assert items[0]["name"] == "Aragorn"

    # Count endpoint
    resp = client.get("/hero/count")
    assert resp.status_code == 200
    assert resp.json() >= 1

    # ── 6. Modify Hero (PUT) ─────────────────────────────────
    updated_payload = hero_payload(
        zone_rid, zone_rev, with_optional=True, is_pydantic=is_pydantic
    )
    updated_payload["name"] = "Elessar"
    updated_payload["level"] = 99
    resp = client.put(f"/hero/{hero_rid}", json=updated_payload)
    assert resp.status_code == 200, (
        f"[{config_name}] update hero failed: {resp.status_code} {resp.text}"
    )
    update_info = resp.json()
    assert update_info["resource_id"] == hero_rid
    # Should have a new revision
    new_rev = update_info["revision_id"]

    # Verify update applied
    resp = client.get(f"/hero/{hero_rid}/data")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Elessar"
    assert data["level"] == 99

    # ── 7. Optional field null ───────────────────────────────
    # Create hero without optional nickname
    payload_no_opt = hero_payload(
        zone_rid, zone_rev, with_optional=False, is_pydantic=is_pydantic
    )
    resp = client.post("/hero", json=payload_no_opt)
    assert resp.status_code == 200, (
        f"[{config_name}] create hero (no opt) failed: {resp.status_code} {resp.text}"
    )
    hero2_rid = resp.json()["resource_id"]

    resp = client.get(f"/hero/{hero2_rid}/data")
    assert resp.status_code == 200
    data2 = resp.json()
    assert data2["nickname"] is None

    # ── 8. Delete Hero ───────────────────────────────────────
    resp = client.delete(f"/hero/{hero_rid}")
    assert resp.status_code == 200, (
        f"[{config_name}] delete hero failed: {resp.status_code} {resp.text}"
    )
    del_meta = resp.json()
    assert del_meta["is_deleted"] is True

    # Verify deleted hero is gone from list
    resp = client.get("/hero/count")
    assert resp.status_code == 200
    # Should be 1 (the second hero) since first is deleted
    assert resp.json() == 1
