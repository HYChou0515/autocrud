# AutoCRUD Web - Makefile
# 常用開發指令

.PHONY: help build-gen gen dev dev-app dev-gen install clean test clean-app gen-app reset-app regen-app style publish

# 預設目標：顯示幫助
help:
	@echo "AutoCRUD Web - 常用指令"
	@echo ""
	@echo "App 管理（推薦）："
	@echo "  make clean-app    - 刪除整個 app 目錄"
	@echo "  make gen-app      - 用 generator 生成全新的 app（需先 build-gen）"
	@echo "  make reset-app    - 刪除 + 重新生成 app（完整重置）"
	@echo "  make regen-app    - 從 AutoCRUD 後端重新生成前端代碼"
	@echo "  make dev-app      - 啟動 app 開發服務器"
	@echo ""
	@echo "開發流程："
	@echo "  make install      - 安裝所有依賴"
	@echo "  make build-gen    - 編譯 generator"
	@echo "  make gen          - 重新生成前端代碼"
	@echo "  make dev          - 啟動開發服務器"
	@echo "  make style        - 自動修復 lint + 格式化（commit 前執行）"
	@echo ""
	@echo "組合指令："
	@echo "  make rebuild      - 重新編譯 generator + 重新生成代碼"
	@echo "  make reset        - 清理 + 安裝 + 編譯 + 生成"
	@echo ""
	@echo "其他："
	@echo "  make clean        - 清理生成的檔案"
	@echo "  make test         - 執行測試"

# 安裝依賴
install:
	@echo "📦 安裝 generator 依賴..."
	cd generator && pnpm install
	@echo "📦 安裝 app 依賴..."
	cd app && pnpm install
	@echo "✅ 安裝完成"

# 編譯 generator
build-gen:
	@echo "🔨 編譯 generator..."
	cd generator && pnpm build
	@echo "✅ Generator 編譯完成"

# 重新生成前端代碼
gen:
	@echo "🚀 重新生成前端代碼..."
	cd app && rm -rf src/generated
	cd app && node ../generator/dist/cli.js generate
	@echo "✅ 代碼生成完成"

# 啟動開發服務器
dev:
	@echo "🚀 啟動開發服務器 (port 5175)..."
	cd app && pnpm dev --port 5175

# 啟動開發服務器（預設端口）
dev-app:
	@echo "🚀 啟動 app 開發服務器..."
	cd app && pnpm dev

# 組合：重新編譯 + 重新生成
rebuild: build-gen gen
	@echo "✅ 重新編譯和生成完成"

# 組合：完整重置
reset: clean install build-gen gen
	@echo "✅ 完整重置完成，可以執行 'make dev' 啟動"

# 清理生成的檔案
clean:
	@echo "🧹 清理生成的檔案..."
	rm -rf generator/dist
	rm -rf generator/node_modules
	rm -rf app/src/generated
	rm -rf app/node_modules
	rm -rf app/dist
	@echo "✅ 清理完成"

# 執行測試
test:
	@echo "🧪 執行測試..."
	cd generator && pnpm test || echo "Generator 沒有測試"
	cd app && pnpm test || echo "App 沒有測試"

# Build production
build: build-gen
	@echo "🏗️  編譯 app 生產版本..."
	cd app && pnpm build
	@echo "✅ 生產版本編譯完成"

# 同步 app → generator/templates/base（排除自動生成的檔案）
sync-templates:
	@echo "📋 同步 app → generator/templates/base..."
	rsync -av --delete \
		--exclude='node_modules' \
		--exclude='.vite' \
		--exclude='.tanstack' \
		--exclude='dist' \
		--exclude='.env' \
		--exclude='pnpm-lock.yaml' \
		--exclude='src/generated' \
		--exclude='src/routes/autocrud-admin' \
		--exclude='src/routeTree.gen.ts' \
		app/ generator/templates/base/
	@echo "✅ Templates 同步完成"

# ============================================================================
# App 管理指令
# ============================================================================

# 刪除整個 app 目錄
clean-app:
	@echo "🔥 刪除 app 目錄..."
	@if [ -d "app" ]; then \
		rm -rf app; \
		echo "✅ app 目錄已刪除"; \
	else \
		echo "⚠️  app 目錄不存在"; \
	fi

# 使用 generator 生成全新的 app
gen-app: build-gen
	@echo "🚀 使用 generator 生成全新的 app..."
	@if [ -d "app" ]; then \
		echo "❌ Error: app 目錄已存在，請先執行 'make clean-app'"; \
		exit 1; \
	fi
	@echo "📂 從模板創建新的 app..."
	cd generator && node dist/cli.js init app --dir ..
	@echo "📦 安裝 app 依賴..."
	cd app && pnpm install
	@echo "🔧 從 AutoCRUD 後端生成代碼..."
	cd app && node ../generator/dist/cli.js generate --url http://0.0.0.0:8000
	@echo "✅ App 生成完成！"
	@echo ""
	@echo "📝 下一步："
	@echo "   cd app"
	@echo "   pnpm dev"

# 完全重置 app：刪除 + 重新生成 + 安裝依賴
reset-app: clean-app gen-app
	@echo "✅ App 完全重置完成！"

# 從 AutoCRUD 後端生成前端代碼
regen-app: build-gen
	@echo "🚀 從 AutoCRUD 後端重新生成前端代碼..."
	@if [ ! -d "app" ]; then \
		echo "❌ Error: app 目錄不存在，請先執行 'make gen-app'"; \
		exit 1; \
	fi
	@echo "🔧 清除舊的生成代碼..."
	rm -rf app/src/generated app/src/routes/autocrud-admin
	@echo "📡 連接到 http://0.0.0.0:8000..."
	cd app && node ../generator/dist/cli.js generate --url http://0.0.0.0:8000
	@echo "✅ 代碼生成完成"

regen-and-run: regen-app dev-app
	@echo "✅ 重新生成並啟動完成！"

# 自動修復 lint + 格式化（commit 前執行一次即可）
style:
	@echo "🎨 Generator: lint --fix + prettier..."
	cd generator && pnpm lint:fix
	cd generator && pnpm format
	@echo "✅ Style 完成"

# 發布 generator 到 npm（style + build + sync templates + publish）
publish: style sync-templates build-gen
	@echo "🚀 發布 generator 到 npm..."
	cd generator && pnpm check
	cd generator && npm publish
	@echo "✅ 發布完成"