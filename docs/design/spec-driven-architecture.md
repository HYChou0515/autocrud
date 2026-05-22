# SpecStar Spec-Driven 架構決議總結

> **狀態**:設計收斂,目標 v0.11 釋出
> **日期**:2026-05-02
> **背景**:專案從 `autocrud` 改名 `specstar`,slogan 改成「Spec-driven backend platform for FastAPI」。本文件是經過完整 grilling 後的策略級決議,給後續開工參考。

---

## 1. 核心定位

SpecStar 從 v0.11 起變成**真正的 spec-driven**:

- User 講 **brief prose**(在 chat 裡描述意圖即可,不需要寫完整的 spec)
- Claude Code skill / `specstar gen` CLI 把 brief prose **展開成完整 `spec.md`**,顯式列出 inferred decisions、breaking change、跟既有 spec 的 diff,**user confirm 後**才寫進檔案
- 確認後的 spec.md 是 source of truth,skill 接著把它翻成 declarative Python(`_generated.py`)+ machine-readable descriptor(`spec.lock.json`)
- 所有 SpecStar engine、Schema API、route templates、storage abstraction、permission system 全部不動,純加 authoring layer 在上

**關鍵**:`spec.md` 不是 user 手寫的東西,是 **skill 跟 user 共筆的合約**——burden 落在 LLM,不在 user。

選擇的「spec-driven」流派是 **(c) AI/LLM SDD**(GitHub Spec Kit / Kiro / Tessl 同類),但有一個關鍵差異化:**目標是 SpecStar 已定義良好的有限 primitive 集**,LLM 只在受限的目標指令集上選擇,不從零生 backend。

---

## 2. Pipeline

```
user brief prose (chat input, 進 commit message)
   ↓ skill 互動展開 + 顯式列出 inferred decisions + user confirm
spec.md (β: heading protocol + prose,source of truth)
   ↓ skill 翻譯 + AST validator + 偵測 breaking change
my_app/_generated.py (declarative Python,進 git,user 不該手改)
   ↓ spec.dump() (deterministic,無 LLM)
spec.lock.json (descriptor + manifest)
```

---

## 3. 架構決議(以策略題為單位)

### 3.1 Source of truth

- **spec.md 是真相**,`_generated.py` 是 skill 維護的衍生物
- 兩者 + `spec.lock.json` 三份檔同時進 git,各自 hash 進 lock 偵測 drift
- **檔案分離**:
  - `my_app/_generated.py` — skill 維護的 declarative Python,user 別手改
  - `my_app/__init__.py` — user 維護,import `_generated` 並 `spec.apply(app)`
  - `my_app/logic/*.py` — user 邏輯(β reference 指向這裡)
  - `my_app/migrations/*.py` — 跨 resource 等複雜 migration(scaffolded、user 寫)
  - `spec.md` — repo 根目錄
  - `spec.lock.json` — repo 根目錄

### 3.2 LLM 角色與安全邊界

- LLM 寫 **declarative Python + pure function**,**絕不**寫 I/O / orchestration / 副作用 code
- 三層安全機制:
  1. **API 設計**:declarative slot(permission expr、QB filter、computed field)用 proxy + operator overloading 建表達式樹
  2. **AST validator**:`_generated.py` 整檔過 allow / block list
     - Allow:specstar / msgspec / typing / enum / datetime / decimal import、純運算 statement、SpecStar API call、operator、comprehensions、whitelist 純 builtin
     - Block:`Try` / `With` / `Raise` / `While` / `Global` / `Nonlocal` / `Async*`、`os`/`subprocess`/`socket`/`requests`/`urllib`/`pathlib` import、`exec`/`eval`/`__import__`/`open` call
  3. **(β) string reference**:有 I/O 的邏輯走 `"my_app.logic.fn_name"` 字串,SpecStar runtime `importlib` 解析;LLM 不直接 import user module
- **Descriptor 是 audit 介面**:每個節點標 `source = declared | expr_tree | ref | scaffolded | generated`,reviewer 一眼看 LLM 寫了多少

### 3.3 Descriptor 格式

- **Property graph**:`{ "nodes": [...], "edges": [...] }` 的 typed JSON
- 節點型別:`resource` / `field` / `schema_version` / `route` / `route_template` / `storage_backend` / `permission_policy` / `action` / `role`
- 邊型別:`has_field` / `references` / `migrates_to` / `validated_by` / `exposes` / `generated_by` / `performs` / `stored_in` / `gates` / `granted_to` / `requires`
- **Field 是節點**(底層),viz 層渲染成 resource box 內嵌行(UML 風格)
- **Path-based ID**(`resource:User`、`field:User.email`、`route:GET /users/{id}`)
- 可選 `stable_id`(rename 救命繩)

### 3.4 spec.md 格式

**β: heading protocol + prose 內容**

- 三層 heading:
  - `# <Project>` — 一份 spec.md 一個
  - `## Resource: <Name>` — 每個 resource 一個 section
  - `### Fields | Permissions | Storage | Workflows | Schema` — 固定五個可選 section name
- 加一個 special section:`## Defaults`(專案層 storage / permission 預設值)
- Section 內 prose / bullet / table 都吃,LLM 自己 normalize
- **Skill 是 spec.md 的主要 author**,user 講 brief prose,skill 展開、prompt confirm。User 也能直接 hand-edit,但會經 skill round-trip normalize

### 3.5 Skill 執行模型

- **手動觸發**(`/specstar` 或 `/specstar regen`),不要 watch mode
- **三 surface**:
  | Surface | 用途 | LLM? |
  |---|---|---|
  | Claude Code skill | 主要,daily authoring | 借 user 既有 session |
  | `specstar gen` CLI | 給非 Claude Code user | 走 ANTHROPIC_API_KEY |
  | `specstar verify` | CI / drift 偵測 | **不用** |
- CI **絕不**跑 LLM(non-deterministic / 要 secret / 慢 / 花錢)。`verify` 純 deterministic 比 hash + 重算 descriptor

### 3.6 Hash-based change detection

`spec.lock.json` 是完整 manifest:

```json
{
  "specstar_version": "0.11.0",
  "skill_version": "0.11.0",
  "sources": {
    "spec.md": { "sha256": "...", "size": ..., "regenerated_at": "..." },
    "_generated.py": { "sha256": "...", "size": ... }
  },
  "descriptor": { "nodes": [...], "edges": [...] },
  "validation": { "ast_check": "passed", "errors": [] }
}
```

Skill 用 hash 進入四個 case:

| Case | spec.md | _generated.py | 行為 |
|---|---|---|---|
| 1 | 沒變 | 沒變 | 「沒事可做。要新增/修改什麼?」 進 brief prose 互動 |
| 2 | 變了 | 沒變 | 偵測改動 → unclear 反問 → 提 plan + confirm → regen |
| 3 | 沒變 | 變了 | drift warning,reconcile dialog |
| 4 | 都變 | | reconcile mode,user 決定優先 |

Hash 計算前正規化(LF / trim trailing / `ruff format`),避免 false drift。

### 3.7 Migration 故事

- spec.md 自己負責 version history(`### Schema versions` section,自然語言描述)
- **LLM 寫 pure-function migration**(input v_n dict → output v_{n+1} dict),AST-validated 確保純度
- Descriptor 在 `migrates_to` edge 掛 `code` property,reviewer 看 prose + code 並排 audit
- **不用 declarative ops**(rename/add-default/drop/coerce 涵蓋率太低,假命題)
- 既有 Schema API 不變(`Schema(...).step("v1", callable)`)
- I/O / cross-resource / 多步驟 migration 走 (β) ref(scaffold + user 寫)
- `### Schema: no versioning` 開關給 dev 期 user 跳過 versioning

---

## 4. v0.11 Scope

| 模組 | 內容 | 變動類型 |
|---|---|---|
| Foundations | `spec.dump()`、descriptor JSON schema、`spec.lock.json` manifest、AST validator(allow/block list) | 新增 |
| CLI | `specstar init` / `status` / `verify` / `gen` | 新增 |
| Skill | `.claude/skills/specstar-spec/SKILL.md` + prompt template | 新增 |
| Schema API | callable migration(現有形式) | **不變** |
| Engine / `spec.add_model()` API | | **不變** |
| Docs | spec-driven workflow guide / AST rules / (β) ref 規範 / migration guide | 新增 |

**對 v0.10 user 的承諾:零 breaking change,純加法**。

---

## 5. Skill (`SKILL.md`) 結構

7 個 section + 3 個 worked examples + 外部參考檔:

1. When to activate
2. Inputs to read first(檔案、順序、hash 比對)
3. Decision tree(case 1-4 by hash state)
4. Plan synthesis protocol(顯式列出 inferred decisions、breaking change 觸發 migration prompt、(β) ref scaffold + reference)
5. Confirmation protocol(明確同意才 proceed、pushback 退回 plan)
6. Write protocol(_generated.py → AST validate → spec.dump() 更新 lock)
7. Constraints(heading protocol、AST 摘要、ref 規範、forbidden behaviors)

**Worked examples**:新增 resource(case 2)、修改 field 觸發 migration(breaking change)、drift reconcile(case 3)。

**失敗恢復必須在 skill 釘死:**

- AST 拒絕 → 報 validation_errors 給 user,不亂猜重試
- User 說「不對」 → 問哪部分,回 plan 階段
- spec.md / _generated.py drift → 列差異,user 決定
- Lock 損壞 → stop,告訴 user 要不要 force regen
- LLM 不確定 prose → **必問**

設計原則:**flow 規範性 + 步內 judgment 原則**,過度規範會變成狀態機,過度描述會 LLM 自由發揮。

---

## 6. 推遲到 v1.0+

- Watch mode(opt-in)
- `init --from-existing`(reverse engineering 既有 Python → spec.md)
- Multi-file `spec/` directory mode
- Web-based descriptor viz
- Cross-resource migration 自動 scaffolding
- 任何對 SpecStar engine 的改動

---

## 7. 既有 user 路徑

| 路徑 | 描述 | 何時 |
|---|---|---|
| A | 不遷,v0.10 風格 Python 直寫繼續 work | v0.11 起 |
| B | 漸進混用,新 resource 用 spec.md,舊 resource 留 Python | v0.11 起 |
| C | 完整遷移(`init --from-existing`) | 等 v1.1 |

---

## 8. 關鍵風險與對策

| 風險 | 對策 |
|---|---|
| Skill / CLI gen 行為不一致 | 抽 prompt template 成共用 module,兩 surface 同源 |
| Descriptor schema 版本管理 | lock 寫 `descriptor_version`,跨版本不 silent migrate;`verify` fail 並提示 user `regen` |
| AST allow-list 太嚴出 false positive | 第一版做寬,觀察一個 release 後收緊;`# specstar: allow` escape hatch |
| LLM 寫的 declarative Python 不一致(同 input 不同 output) | Skill prompt 強調 deterministic style,worked examples 釘風格;CI verify 不用 LLM 所以不會被 variance 影響 |
| User 直接 hand-edit `_generated.py` 後 regen 覆蓋手改 | Hash drift detection(case 3),`/specstar regen` 主動提示 reconcile |

---

## 9. 留待開工時釘的實作細節

(策略上不重要,寫 code 時自然定)

- `_generated.py` 的 import / 排序 / 多 resource layout 約定
- Error message 用詞與細節
- AST validator 的具體實作(`ast.NodeVisitor` 子類)
- Skill prompt 的 token 控管
- Reverse engineering 演算法(v1.1)
- Testing strategy(skill 怎麼測、AST validator 怎麼測、descriptor stability 怎麼測)
- `_generated.py` 命名是否要替代名(`spec.py` / `_specstar.py`)
- Heading 名字是否要 i18n(目前假設英文)

---

## 10. 設計原則(decision lens)

回顧整個 grilling,有幾條原則重複出現,值得釘住作為後續決策的 lens:

1. **不發明新 DSL**。Python 是 SpecStar 的 DSL,YAML 是 lossy projection 不是 source。
2. **LLM 任務越窄越可靠**。limitation,不是 capability,才是 reliability 的來源。
3. **Audit 介面決定信任成本**。descriptor 是 trust transitivity 的關鍵,沒它的話 LLM 介入就要每次 audit 整檔。
4. **Engine 不動原則**。authoring layer 在上、engine 在下,清楚分層才有 backward compat。
5. **Manual triggered, human in the loop**。沒有 watch / 沒有 CI LLM / 沒有 background agent。每個 LLM call 都看得到、能 review。
6. **失敗時 stop and ask,不要 silent recover**。skill 寧可中斷流程問,不要悄悄選一邊。
