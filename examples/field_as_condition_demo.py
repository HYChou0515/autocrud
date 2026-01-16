"""
Field 直接作為條件使用的示範

展示 Field 作為 ConditionBuilder 的用法：
- QB["field"] 等同於 QB["field"].is_truthy()
- ~QB["field"] 等同於 QB["field"].is_falsy()
"""

from autocrud.query import QB


def demo_basic_usage():
    """基本用法示範"""
    print("=== 基本用法 ===\n")

    # 檢查欄位有值
    print("1. 檢查欄位有值（truthy）")
    q1 = QB["verified"].is_truthy()
    q2 = QB["verified"]  # 直接使用 Field
    print("   明確: QB['verified'].is_truthy()")
    print("   簡潔: QB['verified']")
    print(f"   等價: {q1.build() == q2.build()}\n")

    # 檢查欄位為空
    print("2. 檢查欄位為空（falsy）")
    q1 = QB["comment"].is_falsy()
    q2 = ~QB["comment"]  # 使用 ~ 運算符
    print("   明確: QB['comment'].is_falsy()")
    print("   簡潔: ~QB['comment']")
    print(f"   等價: {q1.build() == q2.build()}\n")


def demo_logical_operations():
    """邏輯組合示範"""
    print("=== 邏輯組合 ===\n")

    # AND 操作
    print("1. 查詢已驗證且有 email 的用戶")
    query = QB["verified"] & QB["email"]
    print("   QB['verified'] & QB['email']")
    print(f"   條件數: {len(query.build().conditions)}\n")

    # OR 操作
    print("2. 查詢管理員或已驗證用戶")
    query = QB["is_admin"] | QB["verified"]
    print("   QB['is_admin'] | QB['verified']")
    print(f"   條件數: {len(query.build().conditions)}\n")

    # 複雜組合
    print("3. 複雜條件：(已驗證 AND 有 email) OR 管理員")
    query = (QB["verified"] & QB["email"]) | QB["is_admin"]
    print("   (QB['verified'] & QB['email']) | QB['is_admin']")
    print(f"   條件數: {len(query.build().conditions)}\n")


def demo_with_negation():
    """否定操作示範"""
    print("=== 否定操作 ===\n")

    # 單一否定
    print("1. 查詢未歸檔的資源")
    query = ~QB["archived_at"]
    print("   ~QB['archived_at']")
    print("   等同於: QB['archived_at'].is_falsy()\n")

    # 組合否定
    print("2. 查詢活躍且未刪除的用戶")
    query = (QB["status"] == "active") & ~QB["deleted_at"]
    print("   (QB['status'] == 'active') & ~QB['deleted_at']")
    print(f"   條件數: {len(query.build().conditions)}\n")

    # 多重否定
    print("3. 查詢未歸檔且未刪除的資源")
    query = ~QB["archived_at"] & ~QB["deleted_at"]
    print("   ~QB['archived_at'] & ~QB['deleted_at']")
    print("   兩個 falsy 條件組合\n")


def demo_practical_examples():
    """實際應用示範"""
    print("=== 實際應用 ===\n")

    # 用戶搜尋
    print("1. 查詢有效用戶：已驗證、有 email、未刪除")
    query = QB["verified"] & QB["email"] & ~QB["deleted_at"]
    print("   QB['verified'] & QB['email'] & ~QB['deleted_at']")
    print("   簡潔且易讀！\n")

    # 內容搜尋
    print("2. 查詢已發布的文章：有標題、有內容、未草稿")
    query = (
        QB["title"] & QB["content"] & ~QB["is_draft"] & (QB["status"] == "published")
    )
    print("   QB['title'] & QB['content'] & ~QB['is_draft'] &")
    print("   (QB['status'] == 'published')\n")

    # 權限檢查
    print("3. 查詢有權限的用戶：管理員或（已驗證且有角色）")
    query = QB["is_admin"] | (QB["verified"] & QB["role"])
    print("   QB['is_admin'] | (QB['verified'] & QB['role'])")
    print("   表達權限邏輯非常直觀\n")


def demo_comparison_with_explicit():
    """明確寫法與簡潔寫法比較"""
    print("=== 明確 vs 簡潔寫法 ===\n")

    scenarios = [
        ("有 email", "QB['email']", "QB['email'].is_truthy()"),
        ("沒有備註", "~QB['comment']", "QB['comment'].is_falsy()"),
        (
            "已驗證且活躍",
            "QB['verified'] & QB['is_active']",
            "QB['verified'].is_truthy() & QB['is_active'].is_truthy()",
        ),
        (
            "未刪除且未歸檔",
            "~QB['deleted'] & ~QB['archived']",
            "QB['deleted'].is_falsy() & QB['archived'].is_falsy()",
        ),
    ]

    for desc, short, explicit in scenarios:
        print(f"{desc}:")
        print(f"  簡潔: {short}")
        print(f"  明確: {explicit}")
        print()


def demo_gotchas():
    """注意事項"""
    print("=== ⚠️  注意事項 ===\n")

    print("1. Field 直接使用是 is_truthy，不是 is_true")
    print("   ✓ QB['verified']           # 檢查有值（排除 None, False, 0, '', []）")
    print("   ✗ QB['verified']           # 並非檢查 == True")
    print("   ✓ QB['verified'] == True   # 明確檢查布林值為 True")
    print()

    print("2. ~ 運算符是 is_falsy，不是 NOT")
    print("   ✓ ~QB['comment']           # 檢查為空（匹配 None, False, 0, '', []）")
    print("   ✗ ~QB['comment']           # 並非邏輯 NOT")
    print("   ✓ ~(QB['age'] > 18)        # 邏輯 NOT（條件的否定）")
    print()

    print("3. 雙重否定的語義")
    print("   ~~QB['field']              # NOT(is_falsy) ≈ is_truthy")
    print("   QB['field']                # 直接用更清晰")
    print()


if __name__ == "__main__":
    demo_basic_usage()
    demo_logical_operations()
    demo_with_negation()
    demo_practical_examples()
    demo_comparison_with_explicit()
    demo_gotchas()

    print("=" * 50)
    print("🎉 Field 可以直接作為條件使用，讓查詢更簡潔！")
    print("=" * 50)
