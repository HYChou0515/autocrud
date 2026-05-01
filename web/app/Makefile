# SpecStar Web App Makefile

# 默認目標
.PHONY: help
help:
	@echo "SpecStar Web App 開發工具"
	@echo ""
	@echo "開發工具："
	@echo "  style        格式化程式碼並修復 lint 問題 (prettier + eslint --fix)"
	@echo "  check        檢查程式碼品質（不修改檔案）"
	@echo "  format       格式化程式碼 (prettier)"
	@echo "  lint         執行 lint 檢查並自動修復"
	@echo "  lint-check   執行 lint 檢查（不修改檔案）"
	@echo "  dev          啟動開發服務器"
	@echo "  build        建置生產版本"
	@echo "  preview      預覽生產版本"
	@echo "  generate     重新生成程式碼（需要後端 API 運行）"
	@echo "  clean        清理構建文件"

# === 開發工具 ===

# 格式化並修復 lint 問題
.PHONY: style
style:
	@echo "🎨 格式化程式碼..."
	@pnpm format
	@echo "🔧 修復 lint 問題..."
	@pnpm lint:fix
	@echo "✅ 程式碼格式化完成"

# 檢查程式碼品質（不修改檔案）
.PHONY: check
check:
	@echo "🔍 檢查程式碼格式..."
	@pnpm format:check
	@echo "🔍 檢查 lint..."
	@pnpm lint
	@echo "✅ 程式碼檢查完成"

# 格式化程式碼
.PHONY: format
format:
	@echo "🎨 格式化程式碼..."
	@pnpm format
	@echo "✅ 格式化完成"

# 執行 lint 並自動修復
.PHONY: lint
lint:
	@echo "🔧 執行 lint 並自動修復..."
	@pnpm lint:fix
	@echo "✅ Lint 修復完成"

# 執行 lint 檢查（不修改檔案）
.PHONY: lint-check
lint-check:
	@echo "🔍 檢查 lint..."
	@pnpm lint
	@echo "✅ Lint 檢查完成"

# === 開發服務器 ===

# 啟動開發服務器
.PHONY: dev
dev:
	@echo "🚀 啟動開發服務器..."
	@pnpm dev

# === 建置 ===

# 建置生產版本
.PHONY: build
build:
	@echo "📦 建置生產版本..."
	@pnpm build
	@echo "✅ 建置完成"

# 預覽生產版本
.PHONY: preview
preview:
	@echo "👀 預覽生產版本..."
	@pnpm preview

# === 程式碼生成 ===

# 重新生成程式碼
.PHONY: generate
generate:
	@echo "🔄 重新生成程式碼..."
	@pnpm generate
	@echo "✅ 程式碼生成完成"

# === 清理 ===

# 清理構建文件
.PHONY: clean
clean:
	@echo "🧹 清理構建文件..."
	@rm -rf dist
	@echo "✅ 清理完成"

# 深度清理（包含 node_modules）
.PHONY: clean-all
clean-all: clean
	@echo "🧹 清理 node_modules..."
	@rm -rf node_modules
	@echo "✅ 深度清理完成"
