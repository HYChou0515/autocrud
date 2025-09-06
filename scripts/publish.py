#!/usr/bin/env python3
"""PyPI 發布腳本"""

import subprocess
import sys
from pathlib import Path


def run_command(command, description):
    """執行命令並顯示結果"""
    print(f"\n🔄 {description}")
    print(f"執行: {command}")

    result = subprocess.run(
        command, check=False, shell=True, capture_output=True, text=True
    )

    if result.returncode == 0:
        print(f"✅ {description} 成功")
        if result.stdout:
            print(result.stdout)
    else:
        print(f"❌ {description} 失敗")
        if result.stderr:
            print(result.stderr)
        return False
    return True


def check_prerequisites():
    """檢查發布前置條件"""
    print("🔍 檢查發布前置條件...")

    # 檢查是否有 build
    try:
        import importlib.util

        if importlib.util.find_spec("build") is not None:
            print("✅ build 套件已安裝")
        else:
            raise ImportError
    except ImportError:
        print("❌ 需要安裝 build 套件: uv add build")
        return False

    # 檢查是否有 twine
    try:
        if importlib.util.find_spec("twine") is not None:
            print("✅ twine 套件已安裝")
        else:
            raise ImportError
    except ImportError:
        print("❌ 需要安裝 twine 套件: uv add twine")
        return False

    # 檢查重要文件
    required_files = ["README.md", "LICENSE", "pyproject.toml"]
    for file in required_files:
        if Path(file).exists():
            print(f"✅ {file} 存在")
        else:
            print(f"❌ 缺少 {file}")
            return False

    return True


def clean_build():
    """清理舊的 build 文件"""
    print("\n🧹 清理舊的 build 文件...")

    dirs_to_clean = ["dist", "build", "*.egg-info"]
    for dir_pattern in dirs_to_clean:
        run_command(f"rm -rf {dir_pattern}", f"清理 {dir_pattern}")


def build_package():
    """建置套件"""
    return run_command("python -m build", "建置套件")


def check_package():
    """檢查套件"""
    return run_command("twine check dist/*", "檢查套件")


def upload_to_testpypi():
    """上傳到 TestPyPI"""
    print("\n📤 準備上傳到 TestPyPI...")
    print("請確保您已設定 TestPyPI token:")
    print("1. 前往 https://test.pypi.org/account/login/")
    print("2. 建立 API token")
    print("3. 執行: uv run twine upload --repository testpypi dist/*")

    choice = input("\n是否現在上傳到 TestPyPI? (y/N): ").lower()
    if choice == "y":
        return run_command(
            "twine upload --repository testpypi dist/*",
            "上傳到 TestPyPI",
        )
    return True


def upload_to_pypi():
    """上傳到 PyPI"""
    print("\n📤 準備上傳到 PyPI...")
    print("⚠️  警告: 這將發布到正式的 PyPI！")
    print("請確保您已設定 PyPI token:")
    print("1. 前往 https://pypi.org/account/login/")
    print("2. 建立 API token")
    print("3. 執行: uv run twine upload dist/*")

    choice = input("\n確定要上傳到正式 PyPI 嗎? (y/N): ").lower()
    if choice == "y":
        return run_command("twine upload dist/*", "上傳到 PyPI")
    return True


def main():
    """主函數"""
    print("🚀 AutoCRUD PyPI 發布工具")
    print("=" * 50)

    # 檢查前置條件
    if not check_prerequisites():
        sys.exit(1)

    # 清理舊文件
    clean_build()

    # 建置套件
    if not build_package():
        sys.exit(1)

    # 檢查套件
    if not check_package():
        sys.exit(1)

    print("\n🎉 套件建置完成！")
    print("下一步選項:")
    print("1. 上傳到 TestPyPI (測試)")
    print("2. 上傳到正式 PyPI")
    print("3. 結束")

    choice = input("\n請選擇 (1/2/3): ")

    if choice == "1":
        upload_to_testpypi()
    elif choice == "2":
        upload_to_pypi()
    elif choice == "3":
        print("👋 發布流程結束")
    else:
        print("❌ 無效的選擇")


if __name__ == "__main__":
    main()
