#!/usr/bin/env python3
"""基本權限設定示例

這個範例展示如何在 AutoCRUD 中設定基本的權限控制系統。
包含完整的步驟說明和可執行的程式碼範例。
"""

import datetime as dt
from dataclasses import dataclass

from autocrud.permission.acl import ACLPermission, ACLPermissionChecker, Policy
from autocrud.types import PermissionResult
from autocrud.types import ResourceAction
from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore


# ===== 步驟 1: 定義資料結構 =====
@dataclass
class Document:
    """文檔資料結構"""

    title: str
    content: str
    category: str = "general"


# ===== 步驟 2: 設定基本存儲系統 =====
def setup_storage():
    """設定文檔的存儲系統"""
    # 文檔存儲
    doc_meta_store = MemoryMetaStore()
    doc_resource_store = MemoryResourceStore(Document)
    doc_storage = SimpleStorage(
        meta_store=doc_meta_store,
        resource_store=doc_resource_store,
    )

    return doc_storage


# ===== 步驟 3: 創建權限檢查器 =====
def create_permission_checker():
    """創建 ACL 權限檢查器"""
    # ACLPermissionChecker 會自己管理權限規則的存儲
    return ACLPermissionChecker(
        policy=Policy.strict,  # 嚴格模式：沒有明確允許就拒絕
        root_user="system",  # 系統管理員用戶
    )


# ===== 步驟 4: 設定權限規則 =====
def setup_permissions(permission_checker: ACLPermissionChecker):
    """設定基本的權限規則"""
    current_time = dt.datetime.now()

    # 使用系統管理員身份創建權限規則
    with permission_checker.resource_manager.meta_provide("system", current_time):
        # 管理員擁有所有權限
        admin_permission = ACLPermission(
            subject="admin",  # 誰：管理員
            object="document",  # 對什麼：文檔資源
            action=ResourceAction.read  # 可以做什麼：創建、讀取、更新、刪除
            | ResourceAction.read_list
            | ResourceAction.write
            | ResourceAction.lifecycle,
            effect=PermissionResult.allow,  # 效果：允許
            order=1,  # 優先順序
        )
        permission_checker.resource_manager.create(admin_permission)

        # 編輯者可以創建、讀取和更新，但不能刪除
        editor_permission = ACLPermission(
            subject="editor",
            object="document",
            action=ResourceAction.read
            | ResourceAction.read_list
            | ResourceAction.write,
            effect=PermissionResult.allow,
            order=2,
        )
        permission_checker.resource_manager.create(editor_permission)

        # 讀者只能讀取和搜索
        reader_permission = ACLPermission(
            subject="reader",
            object="document",
            action=ResourceAction.read | ResourceAction.read_list,
            effect=PermissionResult.allow,
            order=3,
        )
        permission_checker.resource_manager.create(reader_permission)

        print("✅ 權限規則設定完成")
        print("   - admin: 完整權限 (CRUD + 搜索)")
        print("   - editor: 創建、讀取、更新、搜索")
        print("   - reader: 讀取、搜索")


# ===== 步驟 5: 創建具備權限控制的 ResourceManager =====
def create_document_manager(doc_storage, permission_checker):
    """創建文檔管理器並整合權限系統"""
    # 創建 ResourceManager 並傳入權限檢查器
    document_manager = ResourceManager(
        resource_type=Document,
        storage=doc_storage,
        permission_checker=permission_checker,  # 關鍵：傳入權限檢查器
    )

    return document_manager


# ===== 步驟 6: 實際使用範例 =====
def demo_permission_system():
    """展示權限系統的實際運作"""
    current_time = dt.datetime.now()

    # 設定系統
    doc_storage = setup_storage()
    permission_checker = create_permission_checker()
    setup_permissions(permission_checker)
    document_manager = create_document_manager(doc_storage, permission_checker)

    print("\n" + "=" * 50)
    print("🚀 開始測試權限系統")
    print("=" * 50)

    # === 測試 1: 管理員創建文檔 ===
    print("\n📝 測試 1: 管理員創建文檔")
    try:
        with document_manager.meta_provide("admin", current_time):
            doc = Document(
                title="管理員文檔",
                content="這是管理員創建的文檔",
                category="admin",
            )
            doc_info = document_manager.create(doc)
            print(f"✅ 成功創建文檔，ID: {doc_info.resource_id}")
    except Exception as e:
        print(f"❌ 失敗: {e}")

    # === 測試 2: 編輯者創建文檔 ===
    print("\n📝 測試 2: 編輯者創建文檔")
    try:
        with document_manager.meta_provide("editor", current_time):
            doc = Document(
                title="編輯者文檔",
                content="這是編輯者創建的文檔",
                category="content",
            )
            doc_info = document_manager.create(doc)
            print(f"✅ 成功創建文檔，ID: {doc_info.resource_id}")
            editor_doc_id = doc_info.resource_id
    except Exception as e:
        print(f"❌ 失敗: {e}")

    # === 測試 3: 讀者嘗試創建文檔（應該失敗）===
    print("\n📝 測試 3: 讀者嘗試創建文檔")
    try:
        with document_manager.meta_provide("reader", current_time):
            doc = Document(title="讀者文檔", content="讀者不應該能創建文檔")
            document_manager.create(doc)
            print("❌ 不應該成功！")
    except Exception as e:
        print(f"✅ 正確拒絕: {e}")

    # === 測試 4: 讀者讀取文檔（應該成功）===
    print("\n📖 測試 4: 讀者讀取文檔")
    try:
        with document_manager.meta_provide("reader", current_time):
            doc_resource = document_manager.get(editor_doc_id)
            print(f"✅ 成功讀取文檔: {doc_resource.data.title}")
    except Exception as e:
        print(f"❌ 失敗: {e}")

    # === 測試 5: 編輯者更新文檔（應該成功）===
    print("\n✏️ 測試 5: 編輯者更新文檔")
    try:
        with document_manager.meta_provide("editor", current_time):
            updated_doc = Document(
                title="更新後的編輯者文檔",
                content="內容已更新",
                category="content",
            )
            document_manager.update(editor_doc_id, updated_doc)
            print("✅ 成功更新文檔")
    except Exception as e:
        print(f"❌ 失敗: {e}")

    # === 測試 6: 編輯者嘗試刪除文檔（應該失敗）===
    print("\n🗑️ 測試 6: 編輯者嘗試刪除文檔")
    try:
        with document_manager.meta_provide("editor", current_time):
            document_manager.delete(editor_doc_id)
            print("❌ 不應該成功！")
    except Exception as e:
        print(f"✅ 正確拒絕: {e}")

    print("\n" + "=" * 50)
    print("🎉 權限系統測試完成")
    print("=" * 50)


# ===== 主要概念說明 =====
def explain_concepts():
    """解釋權限系統的核心概念"""
    print("\n" + "=" * 60)
    print("📚 AutoCRUD 權限系統核心概念")
    print("=" * 60)

    print("\n🔐 ACL 權限模型:")
    print("   Subject (主體) - 誰要執行操作 (user:alice, group:admin)")
    print("   Object (客體)  - 對什麼資源操作 (document, user)")
    print("   Action (動作)  - 要執行什麼操作 (create, read, update, delete)")
    print("   Effect (效果)  - 允許還是拒絕 (allow, deny)")

    print("\n⚙️ 權限檢查流程:")
    print("   1. 用戶發起操作請求")
    print("   2. ResourceManager 攔截請求")
    print("   3. 權限檢查器檢查用戶權限")
    print("   4. 允許則執行，拒絕則拋出異常")

    print("\n🎯 最佳實踐:")
    print("   - 使用最小權限原則")
    print("   - 明確定義角色和權限")
    print("   - 定期檢查和更新權限設定")
    print("   - 記錄重要的權限變更")


if __name__ == "__main__":
    print("🔐 AutoCRUD 基本權限設定示例")
    print("這個範例將展示如何設定和使用基本的權限控制系統")

    # 解釋概念
    explain_concepts()

    # 執行示例
    demo_permission_system()

    print("\n💡 提示：")
    print("   - 修改上面的程式碼來實驗不同的權限設定")
    print("   - 查看 permission.py 了解更多進階功能")
    print("   - 參考 permission_context.py 了解自定義權限檢查器")
