# SpecStar v0.11 實作 Plan

> **參考**:[spec-driven-architecture.md](spec-driven-architecture.md)(策略決議)
> **狀態**:Plan,未開工
> **預估規模**:單人約 3–5 週,可分 ~15 個 PR

---

## Definition of Done(釋出條件)

v0.11 釋出前必須全部勾選:

- [ ] `spec.dump()` 能對註冊好的 SpecStar instance 產出符合 descriptor schema 的 JSON
- [ ] `spec.lock.json` 格式定型,read/write round-trip + hash deterministic
- [ ] AST validator 對既有 SpecStar examples 全部 pass,對 known-bad pattern 全部 reject
- [ ] `specstar verify` / `status` / `init` / `gen` 四個 CLI command 可用
- [ ] `.claude/skills/specstar-spec/SKILL.md` 完成,3 個 worked examples 跑得通
- [ ] 既有 v0.10 testsuite **零 regression**(engine 不動的承諾驗證)
- [ ] 文件:workflow guide + AST rules + (β) ref guide + v0.10→v0.11 migration guide
- [ ] CHANGELOG / 版本號 / migration smoke test 完備

---

## 依賴拓樸

```
Phase 1 (Foundations)
  ├─ 1.1 descriptor schema   ──┬──→ 1.2 spec.dump()
  ├─ 1.5 AST validator       │   ├──→ 1.3 lock.json
  └─ 1.6 escape hatch ──→ 1.5 │   └──→ 1.4 hash normalization
                              ↓
Phase 2 (CLI) ←─ 全部 phase 1 ─→ Phase 3 (Skill) ←─ 部分 phase 1
  ├─ 2.1 entry                  ├─ 3.1 prompt template
  ├─ 2.2 verify                 ├─ 3.2 SKILL.md
  ├─ 2.3 status                 └─ 3.3 integration test
  ├─ 2.4 init
  └─ 2.5 gen ←──────────────── 依賴 3.1
                              ↓
                  Phase 4 (Docs)
                              ↓
                  Phase 5 (Release prep)
```

**並行起點**:1.1 跟 1.5 可同時開工(獨立)。

---

## Phase 1 — Foundations(~ 5–7 天)

### 1.1 Descriptor JSON schema 與內部表示

- **產出**:`specstar/descriptor/types.py`(msgspec.Struct 定義 nodes / edges / manifest)+ `specstar/descriptor/schema.json`(JSON Schema 用於外部驗證)
- **節點型別**:`resource` / `field` / `schema_version` / `route` / `route_template` / `storage_backend` / `permission_policy` / `action` / `role`
- **邊型別**:`has_field` / `references` / `migrates_to` / `validated_by` / `exposes` / `generated_by` / `performs` / `stored_in` / `gates` / `granted_to` / `requires`
- **ID 規則**:path-based(`resource:User`、`field:User.email`),可選 `stable_id`
- **版本**:`descriptor_version: 1` 寫進 manifest
- **Acceptance**:hand-crafted example covers 所有節點/邊型別,JSON Schema validate 通過

### 1.2 `spec.dump_descriptor()` 實作

- **命名注意**:`SpecStar.dump()` 已被既有 API 占用(資源資料 → msgpack 備份)。Spec-driven 用 **`dump_descriptor`** 避免衝突
- **產出**:`SpecStar.dump_descriptor(path: str | Path | None = None) -> Descriptor | None` method on `specstar/crud/core.py`,delegate 到 `specstar/descriptor/builder.py`
- **行為**:走 in-memory state(`add_model` 註冊的 model、route templates、storage、permissions、Schema chains)→ 建 property graph → 回傳 `Descriptor` 或寫 indented JSON 到 path
- **v0.11 minimal coverage**(這 PR):`resource` / `field` 節點 + `has_field` / `references` 邊
- **後續 v0.11 擴充**(同 task,分多個 PR):`schema_version` / `migrates_to` / `route` / `route_template` / `exposes` / `generated_by` / `storage_backend` / `stored_in` / `permission_policy` / `gates` / `granted_to`
- **Acceptance**:integration test 註冊 ~3 個 resources(含 ref、Schema chain、permission),`dump_descriptor()` 產出與 golden snapshot 一致

### 1.3 `spec.lock.json` manifest format + I/O

- **產出**:`specstar/lockfile.py`(read / write / validate)
- **格式**:見 design doc §3.6
- **Acceptance**:read-write round-trip 完全相同;同 input descriptor → 同 sha256(deterministic JSON serialization)

### 1.4 Hash normalization

- **產出**:`specstar/lockfile.py:normalize_*` helpers
- **規則**:
  - spec.md:LF + trim trailing whitespace + 統一 heading 後空格 → `sha256`
  - `_generated.py`:`ruff format` → `sha256`
- **Acceptance**:不同 line ending / trailing space / formatting 風格 → 同 hash

### 1.5 AST validator

- **產出**:`specstar/validator/ast.py`(`ast.NodeVisitor` 子類)
- **Allow / block list**:見 design doc §3.2 表格
- **錯誤格式**:`{ "node": ast.Try, "line": 42, "reason": "Try statement not allowed in declarative Python", "fix_hint": "..." }`
- **Acceptance**:
  - **正向**:既有 examples(`docs/en/...` / `tests/example/`)裡 SpecStar API 用法全部 pass
  - **負向**:測試 fixture 含 `import os` / `Try` / `requests.get` / `__import__("...")` / `exec(...)` / 寫檔 / `socket` 等全部 reject

### 1.6 `# specstar: allow` 註解 escape hatch

- **產出**:1.5 模組擴充
- **行為**:line 結尾或上一行的 `# specstar: allow [<reason>]` 註解 → 該 line / block 跳過 validator
- **Acceptance**:加 escape comment 後 known-bad pattern 從 reject 變 accept,並在 lock 的 `validation` 欄位記錄 `bypassed_lines`

---

## Phase 2 — CLI(~ 4–5 天)

### 2.1 CLI entry point

- **產出**:`specstar/cli/__init__.py`(用 click 或 typer)+ `pyproject.toml` 加 `[project.scripts] specstar = "specstar.cli:main"`
- **Acceptance**:`uv run specstar --help` 列出四個 sub-command

### 2.2 `specstar verify`(無 LLM)

- **產出**:`specstar/cli/verify.py`
- **行為**(全 deterministic):
  1. 讀 spec.lock.json
  2. 比對 spec.md 當前 hash == lock 中的 hash
  3. 比對 `_generated.py` 當前 hash == lock 中的 hash
  4. 載入 `_generated.py`、跑 `spec.dump()`、比對 == lock 中的 descriptor
  5. 跑 AST validator on `_generated.py`
- **Exit code**:0 = pass,非 0 = 列差異
- **Acceptance**:CI workflow YAML 可直接呼叫;故意改一個 hash → exit 1 並印明確訊息

### 2.3 `specstar status`

- **產出**:`specstar/cli/status.py`
- **行為**:報告當前 hash state(case 1/2/3/4),不修改任何檔
- **Acceptance**:四種 case 各自人類可讀的輸出

### 2.4 `specstar init`

- **產出**:`specstar/cli/init.py` + 內建 starter template(在 package 內 `specstar/cli/templates/`)
- **行為**:在當前空目錄產生 `spec.md`(範例 User resource)、`my_app/__init__.py`、`my_app/_generated.py`、`spec.lock.json`、`pyproject.toml` snippet
- **Acceptance**:`uv run specstar init` 後 `uvicorn my_app:app` 即可起 server,GET /users 回應 200

### 2.5 `specstar gen`

- **產出**:`specstar/cli/gen.py`
- **依賴**:Phase 3.1(prompt template)
- **行為**:讀 `ANTHROPIC_API_KEY`,呼叫 Claude API,執行跟 skill 同樣的流程(讀 spec.md / `_generated.py` / lock → diff → 提 plan → user 確認 → 寫檔 → AST validate → 更新 lock)
- **互動模式**:terminal prompt(stdin / stdout),不是 chatbot UI
- **Acceptance**:同樣 spec.md 變動透過 `gen` 與透過 Claude Code skill 產出一致(忽略 LLM 隨機性)

---

## Phase 3 — Skill(~ 5–7 天)

### 3.1 Prompt template 模組

- **產出**:`specstar/skill/prompts.py`
- **內容**:給定當前 state(spec.md / `_generated.py` / lock 內容、hash diff、user brief prose)→ 組出完整 system + user prompt
- **共用**:Claude Code skill 跟 `specstar gen` 都呼叫此模組,確保兩 surface 行為一致
- **Acceptance**:單元測試 cover 各種 state(case 1/2/3/4 + breaking change)各產出對應 prompt

### 3.2 SKILL.md 撰寫

- **產出**:`.claude/skills/specstar-spec/SKILL.md`(7 sections + 3 worked examples,見 design doc §5)
- **外部 reference**:`.claude/skills/specstar-spec/ast_rules.md`(AST 細則完整版)
- **Acceptance**:長度 300–500 行;在 Claude Code 中可被 `/specstar` 觸發;3 worked examples 涵蓋新增 resource / 修改 field 觸發 migration / drift reconcile

### 3.3 Skill integration testing

- **產出**:`tests/skill/`(可能用 anthropic Python SDK 或本地 Claude API mock)
- **方法**:給定 `(初始 state, brief prose)`,跑 skill,assert 終態 lock 跟 golden snapshot 一致
- **Acceptance**:至少 5 個 end-to-end test pass(對應 3 worked examples + 2 edge cases)
- **取捨**:LLM 隨機性可能讓 strict golden 失敗 → 用 structural assertion(node/edge 集合相等,允許措辭差異)

---

## Phase 4 — Docs(~ 3–4 天)

### 4.1 spec-driven workflow guide

- **產出**:`docs/en/spec-driven/quickstart.md` + `docs/en/spec-driven/workflow.md`
- **內容**:`specstar init` → 寫 brief → `/specstar` → 看 diff → commit。完整跑一次 ~5 個 resource 的範例
- **Acceptance**:user 照著做能跑出 working app

### 4.2 AST validator reference

- **產出**:`docs/en/spec-driven/ast-rules.md`
- **內容**:allow / block list 完整表格、每條 rule 的 rationale、`# specstar: allow` 用法、常見誤觸 + 解法
- **Acceptance**:完整覆蓋 1.5 的規則表格

### 4.3 (β) reference guide

- **產出**:`docs/en/spec-driven/logic-references.md`
- **內容**:何時該用 (β) ref vs 讓 LLM 寫 declarative、Python module 命名、簽名規範、scaffold 流程
- **Acceptance**:含 worker / custom permission / cross-resource migration 三個範例

### 4.4 v0.10 → v0.11 migration guide

- **產出**:`docs/en/migration/v0.10-to-v0.11.md`
- **內容**:三條既有 user 路徑(A/B/C from design doc §7);強調 zero breaking change
- **Acceptance**:cover 既有 example 的轉換場景

### 4.5 README / landing 更新

- **產出**:repo 根 `README.md`、`docs/en/index.md`
- **內容**:加 spec-driven 範例(`spec.md` snippet → working API)、保留現有 `spec.add_model()` 範例(共存)
- **Acceptance**:首頁就能看到 spec-driven 是 v0.11 主打

---

## Phase 5 — Release prep(~ 1–2 天)

### 5.1 CHANGELOG

- 條列新增 / 不變 / 推遲清單

### 5.2 版本號

- `specstar/__init__.py`:`__version__ = "0.11.0"`
- `pyproject.toml` 同步

### 5.3 Migration smoke test

- 拿 v0.10 era 的 example app(若 git 有 tag,checkout v0.10)
- 用 v0.11 跑,確認零 regression
- 跑 `specstar init --from-existing`(若 v0.11 含此功能,目前 design 推遲到 v1.1)→ 略過

### 5.4 Release(由你執行,不在自動範圍)

- `make build`、`uv publish` 到 PyPI
- GitHub release notes
- 部落格 / 社群推廣(可選)

---

## 開工時會浮現的實作決策(目前刻意保留彈性)

- `_generated.py` 的 import 排序、resource 在檔案內的順序(alphabetical?dependency order?)
- Skill prompt 的 token budget(若 spec.md 很大,要不要分段傳)
- AST validator 的具體 allow-list 是否要為 `datetime.datetime.now()` 之類**有副作用但被普遍認為「無害」的 builtin** 留特例
- Lock file 是否壓縮(JSON pretty vs compact)
- `_generated.py` 是否要加 `# AUTOGENERATED — DO NOT EDIT` header
- Heading 名稱是否支援中文 i18n(目前假設英文)
- Worked examples 用 User / Order / Product 還是更具體的 domain

這些都是寫到那段才有 context 釘對,不要先決定。

---

## 風險清單(執行時注意,參考 design doc §8)

| 風險 | 檢核時機 | 對策 |
|---|---|---|
| AST allow-list 太嚴 false positive | Phase 1.5 + Phase 4(docs review) | 第一版做寬,觀察 release 1 個月後收緊 |
| Skill / `gen` 行為飄移 | Phase 3.3 integration tests | 共用 prompt 模組(Phase 3.1) |
| Descriptor schema 改動破壞既有 lock | 任何 Phase 1 改動後 | `descriptor_version` bump → `verify` 提示 user 跑 `regen` |
| `_generated.py` 被手改 | 文件警告 + Phase 2.3 status command 偵測 | drift case 3/4 reconcile dialog |
| LLM 寫的 declarative Python 不一致 | Phase 3.3 | 結構性 assertion + Skill prompt 強調 deterministic style |

---

## 開工建議第一步

**最輕量、最高槓桿、能立刻讓專案動起來的第一個 PR**:

> **PR #1: Phase 1.1(descriptor schema)+ 1.5 部分(AST validator 骨架)**
>
> - 加 `specstar/descriptor/types.py` 跟 `specstar/validator/ast.py` 兩個模組(空 + 型別簽名 + 一兩個 minimal struct)
> - 加 `tests/descriptor/test_types.py` 跟 `tests/validator/test_ast.py`
> - 不改 `specstar/__init__.py`,不 expose,純內部
> - PR ~ 200 行,review 容易,確立模組結構

之後 1.2 / 1.3 / 1.4 / 1.5 完整版 / 1.6 各自 1 個 PR,Phase 1 結束時約 6 個 PR,所有後續 phase 都站在 Phase 1 之上。

---

## 不在這份 plan 內的東西

- 任何 v0.11 之後的功能(watch mode / reverse engineering / multi-file spec / web viz),參考 design doc §6
- SpecStar engine 內部任何 refactor(原則:engine 不動)
- 商業 / 行銷 / OSS 策略
