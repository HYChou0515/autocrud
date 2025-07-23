"""測試 Memory 和 Disk 存儲的差異"""

import os
import tempfile
from dataclasses import dataclass
from autocrud import AutoCRUD, MemoryStorage, DiskStorage


@dataclass
class Book:
    title: str
    author: str
    price: float


def test_memory_vs_disk_storage():
    """比較 Memory 和 Disk 存儲的差異"""
    print("=== Memory vs Disk 存儲比較 ===")

    # 測試數據
    books_data = [
        {"title": "Python 程式設計", "author": "張三", "price": 450.0},
        {"title": "Web 開發實戰", "author": "李四", "price": 520.0},
        {"title": "資料結構", "author": "王五", "price": 380.0},
    ]

    # 1. 測試純內存存儲
    print("\n1. 測試純內存存儲（Memory Storage）")
    memory_storage = MemoryStorage()
    memory_crud = AutoCRUD(model=Book, storage=memory_storage, resource_name="books")

    # 創建書籍
    memory_books = []
    for book_data in books_data:
        book = memory_crud.create(book_data)
        memory_books.append(book)
        print(f"內存創建: {book['title']}")

    print(f"內存存儲大小: {memory_storage.size()}")
    print(f"內存所有鍵: {memory_storage.list_keys()}")

    # 2. 測試磁碟存儲
    print("\n2. 測試磁碟存儲（Disk Storage）")
    temp_dir = tempfile.mkdtemp()
    print(f"磁碟存儲目錄: {temp_dir}")

    disk_storage = DiskStorage(temp_dir)
    disk_crud = AutoCRUD(model=Book, storage=disk_storage, resource_name="books")

    # 創建書籍
    disk_books = []
    for book_data in books_data:
        book = disk_crud.create(book_data)
        disk_books.append(book)
        print(f"磁碟創建: {book['title']}")

    print(f"磁碟存儲大小: {disk_storage.size()}")
    print(f"磁碟所有鍵: {disk_storage.list_keys()}")

    # 檢查實際檔案
    files = os.listdir(temp_dir)
    print(f"實際檔案: {files}")

    # 3. 模擬重啟：重新創建存儲實例
    print("\n3. 模擬應用重啟")

    # 內存存儲：數據消失
    print("重新創建內存存儲...")
    new_memory_storage = MemoryStorage()
    new_memory_crud = AutoCRUD(
        model=Book, storage=new_memory_storage, resource_name="books"
    )

    memory_books_after_restart = new_memory_crud.list_all()
    print(f"重啟後內存書籍數量: {len(memory_books_after_restart)} (數據消失)")

    # 磁碟存儲：數據保持
    print("重新創建磁碟存儲...")
    new_disk_storage = DiskStorage(temp_dir)
    new_disk_crud = AutoCRUD(
        model=Book, storage=new_disk_storage, resource_name="books"
    )

    disk_books_after_restart = new_disk_crud.list_all()
    print(f"重啟後磁碟書籍數量: {len(disk_books_after_restart)} (數據保持)")

    for book_id, book in disk_books_after_restart.items():
        print(f"保持的書籍: {book['title']}")

    # 4. 性能比較
    print("\n4. 簡單性能比較")
    import time

    # 內存存儲性能
    start_time = time.time()
    for i in range(100):
        memory_storage.set(f"test:{i}", {"data": f"test_value_{i}"})
    memory_time = time.time() - start_time

    # 磁碟存儲性能
    start_time = time.time()
    for i in range(100):
        disk_storage.set(f"test:{i}", {"data": f"test_value_{i}"})
    disk_time = time.time() - start_time

    print(f"內存存儲 100 次寫入: {memory_time:.4f} 秒")
    print(f"磁碟存儲 100 次寫入: {disk_time:.4f} 秒")
    print(f"磁碟比內存慢: {disk_time / memory_time:.1f} 倍")

    # 5. 清理
    print("\n5. 清理測試數據")
    disk_storage.clear()
    remaining_files = os.listdir(temp_dir)
    print(f"清理後剩餘檔案: {remaining_files}")

    # 刪除臨時目錄
    os.rmdir(temp_dir)
    print("已刪除臨時目錄")


def demo_use_cases():
    """展示不同使用場景"""
    print("\n=== 使用場景展示 ===")

    print("\n📋 使用場景建議:")
    print("1. MemoryStorage - 適合:")
    print("   • 單元測試和集成測試")
    print("   • 快速原型開發和演示")
    print("   • 臨時緩存和會話數據")
    print("   • 不需要持久化的場景")

    print("\n2. DiskStorage - 適合:")
    print("   • 小到中型應用的數據存儲")
    print("   • 配置文件和設置數據")
    print("   • 本地文件存儲需求")
    print("   • 需要數據持久化的場景")

    print("\n3. 未來 S3Storage - 適合:")
    print("   • 雲端應用和分佈式系統")
    print("   • 大規模數據存儲")
    print("   • 需要高可用性的場景")


if __name__ == "__main__":
    test_memory_vs_disk_storage()
    demo_use_cases()
