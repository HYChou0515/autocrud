#!/bin/bash
# 文檔部署腳本
# 用於本地測試和手動部署到 GitHub Pages

set -e

echo "🚀 開始構建 AutoCRUD 文檔..."

# 檢查依賴
echo "📦 檢查依賴..."
if ! uv run mkdocs --version &> /dev/null; then
    echo "❌ MkDocs 未安裝，正在安裝..."
    uv sync --group docs
fi

# 清理舊的構建文件
echo "🧹 清理舊文件..."
make clean-docs

# 構建 HTML 文檔
echo "🔨 構建 MkDocs 文檔..."
make docs

# 檢查構建結果
if [ -f "site/index.html" ]; then
    echo "✅ 文檔構建成功！"
    echo "📂 文檔位置: $(pwd)/site/"
    echo "🌐 可以用以下命令啟動本地服務器:"
    echo "   make serve"
    echo "   或者直接打開: file://$(pwd)/site/index.html"
else
    echo "❌ 文檔構建失敗！"
    exit 1
fi

# 可選：部署到 GitHub Pages
read -p "🚀 是否部署到 GitHub Pages？(y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "📤 部署到 GitHub Pages..."
    make deploy-docs
fi

echo "🎉 文檔處理完成！"

