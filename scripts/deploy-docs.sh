#!/bin/bash
# 文檔部署腳本
# 用於本地測試和手動部署

set -e

echo "🚀 開始構建 AutoCRUD 文檔..."

# 檢查依賴
echo "📦 檢查依賴..."
if ! command -v sphinx-build &> /dev/null; then
    echo "❌ Sphinx 未安裝，正在安裝..."
    uv add --dev sphinx myst-parser furo sphinx-autodoc-typehints linkify-it-py
fi

# 清理舊的構建文件
echo "🧹 清理舊文件..."
make clean

# 構建 HTML 文檔
echo "🔨 構建 HTML 文檔..."
make html

# 檢查構建結果
if [ -f "docs/build/html/index.html" ]; then
    echo "✅ 文檔構建成功！"
    echo "📂 文檔位置: $(pwd)/docs/build/html/"
    echo "🌐 可以用以下命令啟動本地服務器:"
    echo "   make serve"
    echo "   或者直接打開: file://$(pwd)/docs/build/html/index.html"
else
    echo "❌ 文檔構建失敗！"
    exit 1
fi

# 可選：檢查連結
read -p "🔗 是否檢查文檔連結？(y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🔍 檢查文檔連結..."
    make linkcheck
fi

echo "🎉 文檔部署完成！"
