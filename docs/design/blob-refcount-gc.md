# Blob Ref-Count 與歸零回收設計

> **狀態**:Phase 1(reconcile 核心)+ Phase 2(incremental 優化)均已實作並測試
> **日期**:2026-06-26
> **Issue**:[#370](https://github.com/HYChou0515/autocrud/issues/370) — 「binary 需要紀錄 ref count 並在歸零時 remove」
> **背景**:blob 內容定址去重、跨 model 共用、且目前**永不刪除**。`permanently_delete` 清掉 revision 後,只被該 resource 引用的 blob 變成 orphan 卻仍留在 store,儲存空間無限膨脹。本文件是這個回收機制的設計決議,供實作參考。

## 實作進度

**Phase 1 — reconcile 核心(已完成):**

- `IBlobStore` 新增原語:`delete`、`quarantine`、`restore_from_quarantine`、
  `iter_quarantined`、`iter_active`、`get_mtime`,以及 `get`/`exists` 在活躍區 miss 時
  fall-through 隔離區。三個 backend(Memory/Disk/S3)全數實作。
- `ResourceManager.collect_all_referenced_file_ids()`:權威重掃,回傳 `(file_ids, complete)`。
- `SpecStar.gc(mode="reconcile", t1, t2, now)`:跨 model live 聯集 → T1 freshness gate →
  可逆隔離 → restore 被引用者 → 隔離待過 T2 且 scan 完整才 unlink。回傳 `GcStats`。

**Phase 2 — incremental 優化(已完成):**

- `IBlobStore` 再加 `incref`、`decref`、`touch`、`iter_orphan_candidates`(後者由
  `BasicBlobStore` 提供共用實作)。candidate 集合為**行程內、盡力、非持久**,由
  `decref` 歸零時填入、`incref`/`quarantine`/`delete` 清除。
- 接線:`permanently_delete` 先對自己 resource 的每個 (revision, file_id) `decref`;
  寫入路徑 `_process_binary_fields` 對每個 (revision, file_id) 做
  resurrection + `incref` + `touch`(全 best-effort try/except,絕不讓記帳搞垮寫入)。
- `SpecStar.gc(mode="incremental", t1, now)`:只掃 candidate 集合(不掃 revision),
  對 age>T1 者 `quarantine`,**從不 unlink**。
- 測試:blob store 契約(touch/candidate)+ crud 端到端(incremental 隔離→reconcile 刪除、
  count 驅動跳過仍被引用者、寫入路徑即時 resurrection)。

> **與 #387 的潛在衝突**:#387 將 disk store 改為 `_sh/<ab>/<cd>/` sharding。本實作的
> Disk `iter_active`/隔離區/`.refcount`/`.blobmeta` 假設 flat layout;合併時需讓
> `iter_active` 掃進 sharded 子目錄、並把 `_quarantine/`/`_refcount/` 與 `_sh/` 的
> reserved 前綴對齊。

---

## 1. 問題與約束

現況(已從程式碼確認):

- **內容定址 + 去重**:`put(data)` 用 `xxh3_128` hash 當 `file_id`(`blob_store/simple.py`、`s3.py`)。相同內容在不同 resource / revision / model 都對映到**同一個 blob**。
- **`IBlobStore` 沒有 delete**:blob 至今永不刪除(`resource_manager/basic.py`)。
- **revision 不可變、從不單獨刪除或 pruning**:唯一會丟掉 blob 引用的操作是 `permanently_delete(resource_id)` → `purge_resource`(清掉該 resource 的所有 revision)。soft delete 不動 revision,因此不產生 orphan。
- **`BinaryProcessor.collect_file_ids()` 已存在**:目前只用在 `dump()` 匯出。可直接複用來推導引用集合。
- **blob store 跨所有 model 共用**:`crud/core.py` 把**同一個 `self.blob_store`** 傳給每一個 model 的 `ResourceManager`。

三個關鍵約束塑造了整個設計:

1. **去重**:同一份 bytes 處處同一個 `file_id`,所以即使 `put` 因去重變成 no-op,也得記一次引用。
2. **唯一減少引用的事件**:`permanently_delete`。
3. **沒有原子計數器原語**(尤其純 S3 無法原子自增)。

---

## 2. 核心取捨:近似計數 + 權威推導

**不做精確的原子計數。** 改採 hybrid:

- **近似 count**(盡力、非原子)當**便宜的預篩**——只負責快速篩出「orphan 嫌疑犯」。
- **權威真相一律靠重掃 revision 資料**(複用 `collect_file_ids`)當場推導——這是去重後唯一可信的 ground truth。

決定性的不對稱性:

> **洩漏(blob 該刪沒刪)可被下次掃描回收;誤刪(blob 還被引用卻刪了)是不可復原的資料遺失。**

因此硬約束:**近似 count 永遠不能單獨授權「真正的 unlink」。** count 只是嫌疑犯名單,任何不可逆的刪除前都必須通過權威推導。

> 為什麼不維護反向索引(`file_id → 引用它的 revisions`)?因為精確索引的基數本身就是精確 count,等於把我們想避開的原子化負擔搬回來。權威真相一律當場重掃,索引免維護。

---

## 3. 生命週期

```
[活躍區]  put / 引用時 touch 刷新 mtime;引用時 incref(盡力、非原子)
   │  permanently_delete(rid):
   │     對「自己這個 resource 的 revisions」collect_file_ids → 逐個 decref(盡力)
   │     降到 <=0 者丟進 pending-candidates 集合      ← 熱路徑到此為止,極快
   │
   │  ===== gc(incremental):便宜、不掃 revision =====
   │     只看 pending 集合,age > T1 者 ── 搬移(可逆)──▶
   ▼
[隔離區資料夾]  記錄進入時間
   │  reference 事件碰到它 → resurrection:搬回活躍 + incref + touch
   │
   │  ===== gc(reconcile):唯一權威全掃,唯一會 unlink =====
   │     掃所有 model 的所有 revision → 全域 live 聯集 + 精確 count
   │       ① 回填 / 修正所有 count(含既有 blob,免遷移腳本)
   │       ② 仍在 live 聯集卻被隔離的 → restore
   │       ③ 新發現的 orphan → 搬進隔離(起算 T2)
   │       ④ 隔離區待過 T2 且確認不在 live 聯集 → unlink
   ▼
真正 unlink(不可逆,只在這裡)
```

### 防禦層(為什麼不會誤刪)

1. 近似 count 只是預篩,永不單獨授權刪除。
2. `age`(T1)擋住「上傳→引用」「假歸零」的暫時窗口。
3. 隔離是**可逆搬移**,不是硬刪。
4. resurrection:任何再引用當場把 blob 拉回活躍。
5. unlink 前必過 reconcile 的**權威全掃**確認。
6. 洩漏可被下次 reconcile 回收;誤刪零容忍。

---

## 4. `age` 定義(定義 A:量「新不新」)

`age = now − blob 的最後寫入時間(原生 mtime / LastModified)`。

`age` 的職責是補上「**有人引用了這個 blob**」與「**count 追上來反映這個引用**」之間的非原子落差。一個 `count <= 0` 的 blob 正常情況下沒人 touch、mtime 自然停滯、於是老化被掃;唯一會 touch 一個 `count <= 0` blob 的事件,就是「新引用正在進來」(同時也是一次 incref)。

逐 backend 落地(幾乎免費,因為各 backend 原生就有最後修改時間):

| backend | mtime 來源 | touch 方式 |
| --- | --- | --- |
| Disk | 檔案 `stat().st_mtime` | `os.utime`(去重命中 skip 寫檔時補一次) |
| S3 | 物件 `LastModified` | 帶資料 put 自然刷新;純 file_id 引用付一次 self `copy_object` 硬刷 |
| Memory | dict entry 時戳 | 覆寫時戳 |

**每次引用都 touch**,所有 backend、所有情況(含 S3 的 self-copy),換取 `age` 閘在任何情況都成立,不依賴下游 resurrection 去補。

> 否決的「定義 B」:`age = now − 上次變 orphan 的時間`。它想擋的 dereference→recreate race 已被「隔離可逆 + resurrection + reconcile 權威全掃」三道閘接住,不值得為它付「歸零時寫戳記 + 維護模糊狀態」的代價。

---

## 5. 兩段門檻

| 門檻 | 階段 | 預設 |
| --- | --- | --- |
| **T1** | 活躍 → 隔離(進隔離的 age 下限) | 1h |
| **T2** | 隔離 → unlink(在隔離區待的時間下限) | 24h |

門檻當 `gc()` 參數傳、給合理預設,不存成全域狀態,讓不同排程能用不同 policy。

---

## 6. 架構(X):blob store 持有原語,crud 編排

權威推導要掃的是 revision,而 revision 只有 `ResourceManager` / `storage` 看得到、blob store 看不到。所以**編排在 crud 層級**,但 count / mtime / 隔離區 / 搬移 / unlink 這些**原語在 blob store**。

### 6.1 `IBlobStore` 新增面

| 方法 | 階段 | 各 backend 落地 |
| --- | --- | --- |
| `incref(file_id) / decref(file_id)` | 記帳(盡力、非原子) | Memory: dict;Disk: 寫進 `.blobmeta` sidecar;S3: object metadata / tag |
| `touch(file_id)` | 引用時刷新 age | Disk `utime` / S3 self-copy / Memory 時戳 |
| `quarantine(file_id)` | gc 階段1 動作 | Disk: 搬到 `_quarantine/`;S3: 搬到 `{prefix}_quarantine/`;記隔離時間 |
| `iter_quarantined(older_than)` | gc 階段2 輸入 | 隔離區待過 `older_than` 者 |
| `restore_from_quarantine(file_id)` | resurrection | 搬回活躍區 |
| `delete(file_id)` | gc 階段2 動作(不可逆) | 真正 unlink |

`get` / `exists` 在**活躍區 miss 時** fall through 隔離區(miss 本來就是罕見/錯誤路徑,這層只是保險,命中活躍區零開銷)。

**count 單位 = per-revision 出現次數**(`collect_file_ids` 回傳 set,故同一 revision 內多欄位算一次):

- `incref`:每存一個引用它的 revision +1。
- `decref`:`permanently_delete` 時按「該 resource 內引用它的 revision 數」遞減。
- reconcile 的精確 count = 所有 model 中引用該 file_id 的 revision 數,與 incref/decref 單位一致。

### 6.2 熱路徑:resurrection

reference 事件(帶資料的 put、`process` 裡的 file_id 純引用驗證)一旦在隔離區找到該內容,當場 **resurrection:搬回活躍區 + incref + touch**。任何真正的再引用都會立刻把 blob 拉出隔離,無鎖地關掉「gc 掃描 vs 並行 create」的 race。`reconcile` 階段2 也會把「掃出來其實仍在 live 聯集」的隔離 blob `restore` 回去,當雙保險。

---

## 7. 編排:`crud.gc(mode, t1, t2) -> stats`

掛 **crud 物件**(它才同時握有 `self.blob_store` 與全部 `resource_managers`)。

- `permanently_delete` 只做最便宜的 best-effort `decref` + 把降到 <=0 的 file_id 丟進 pending-candidates 集合,立刻返回 — 熱路徑永不碰搬移與掃描。
- **`gc(mode="incremental")`**:只看 pending 集合,對 `age > T1` 者 `quarantine`。**不掃 revision、不 unlink。** 純記帳驅動。
- **`gc(mode="reconcile")`**:唯一的權威全掃,也是**唯一會 unlink** 的地方。掃**所有 model** 的所有 revision → 全域 live 聯集 + 精確 count,一趟做完:回填/修正 count、restore 錯置隔離、quarantine 新 orphan、unlink「隔離待過 T2 且不在 live 聯集」者。

> live 聯集 = **所有 model 的聯集**,缺一不可。否則某 model 的 gc 會把「其實被別的 model 引用」的共用 blob 誤判 orphan。

使用者自行排程(incremental 常跑、reconcile 偶爾跑);**library 不自己開背景執行緒**。

---

## 8. 已決定但記錄為約束 / 預設

1. **顯式 key 的 blob**(非內容定址、可能被 out-of-band 引用):reconcile 的 live 聯集只看得到「透過 resource `Binary` 欄位」的引用。若有人手動 `put(key=...)` 並在模型外引用,會被誤判 orphan。**文件化「GC 只管透過 resource 模型引用的內容定址 blob」**。
2. **blob store 不可被多個獨立 crud app 共用**:否則 live 聯集不完整、會誤刪跨 app 的引用。**文件化帶過**,不在 gc 內強制偵測。
3. **並行兩個 reconcile**:靠 best-effort advisory lock(Disk `flock` / Memory lock)避免;S3 不強制。撞上也只是重工,idempotent,不丟資料。
4. **pending-candidates 集合**:盡力、非持久亦可 — 重啟掉了沒關係,reconcile 全掃會補回。
5. **崩潰中斷的搬移**(半搬狀態):由 reconcile 的全掃自我修復。
6. **soft delete 不釋放 blob**:soft-deleted resource 的 revision 仍存在 → 其 blob 仍在 live 聯集 → 保持存活(與「soft delete 可復原」一致)。只有 `permanently_delete` 才會讓 blob 走向回收。

---

## 9. 設計不變式(實作與測試的驗收基準)

1. **絕不誤刪**:被任一存活 revision(任一 model、含 soft-deleted)引用的 blob,在任何 gc 之後仍可讀。
2. **最終回收**:一個 blob 在「最後一個引用它的 revision 被 `permanently_delete`」之後,經過足夠時間 + 至少一次 reconcile,必被 unlink。
3. **可逆性**:unlink 之前的每一步(quarantine)都可由 resurrection / restore 還原。
4. **冪等 / 可重入**:gc(任一模式)中斷後重跑,結果與未中斷一致;重複跑不造成額外效果。
5. **熱路徑零回歸**:活躍區命中的 `get` / `exists` / `put` 不因本功能增加 I/O。
