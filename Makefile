# AutoCRUD 開發與文檔 Makefile

# 變數設定
SPHINXOPTS    ?=
SPHINXBUILD  ?= uv run sphinx-build
SOURCEDIR    = docs/source
BUILDDIR     = docs/build

# 默認目標
.PHONY: help
help:
	@echo "AutoCRUD 開發與文檔工具"
	@echo ""
	@echo "開發工具："
	@echo "  test         執行所有測試（排除基準測試）"
	@echo "  test-benchmark 執行基準測試（需要外部系統依賴）"
	@echo "  coverage     執行測試並生成覆蓋率報告"
	@echo "  cov-html     生成 HTML 覆蓋率報告"
	@echo "  style        格式化程式碼並修復程式碼風格問題 (ruff format + ruff check --fix)"
	@echo "  check        檢查程式碼品質 (ruff check)"
	@echo "  format       格式化程式碼 (ruff format)"
	@echo "  lint         執行 lint 檢查"
	@echo "  install      安裝專案依賴"
	@echo "  dev-install  安裝開發依賴"
	@echo "  build        建置套件"
	@echo "  publish      發布套件到 PyPI"
	@echo "  clean        清理所有暫存和構建文件 (clean-dev + clean-docs)"
	@echo "  clean-dev    清理開發暫存檔案"
	@echo ""
	@echo "文檔工具："
	@echo "  html         構建 HTML 文檔"
	@echo "  clean-docs   清理文檔構建文件"
	@echo "  serve        啟動本地文檔服務器"
	@echo "  linkcheck    檢查文檔中的連結"
	@echo "  all-docs     構建所有文檔格式"
	@echo ""
	@echo "複合指令："
	@echo "  quality      完整的程式碽品質檢查 (style + check + test)"
	@echo "  dev          快速開發循環 (style + test)"
	@echo "  ci           CI/CD 流程 (check + test + coverage)"
	@echo "  full-check   完整檢查 (dev-install + quality + coverage)"

# === 開發工具 ===

# 安裝依賴
.PHONY: install
install:
	@echo "安裝專案依賴..."
	uv sync

# 安裝開發依賴
.PHONY: dev-install
dev-install:
	@echo "安裝開發依賴..."
	uv sync --dev

# 執行測試（排除基準測試）
.PHONY: test
test: check
	@echo "執行測試（排除基準測試）..."
	uv run coverage run --branch -m pytest -m "not benchmark"
	uv run coverage report -m

# 執行基準測試
.PHONY: test-benchmark
test-benchmark:
	@echo "執行基準測試（需要外部系統依賴）..."
	uv run pytest -m "benchmark" -v

# 執行測試並生成覆蓋率報告
.PHONY: coverage
coverage: test
	@echo "生成覆蓋率報告..."

# 生成 HTML 覆蓋率報告
.PHONY: cov-html
cov-html: coverage
	@echo "生成 HTML 覆蓋率報告..."
	uv run coverage html
	@echo "HTML 報告已生成在 htmlcov/ 目錄"

# 程式碼格式化和修復
.PHONY: style
style:
	@echo "格式化程式碼並修復程式碼風格問題..."
	uv run ruff format .
	uv run ruff check --fix .

# 檢查程式碼品質
.PHONY: check
check:
	@echo "檢查程式碼品質..."
	uv run ruff check .
	uv run ruff format --check

# 格式化程式碼
.PHONY: format
format:
	@echo "格式化程式碼..."
	uv run ruff format .

# Lint 檢查
.PHONY: lint
lint: check
	@echo "Lint 檢查完成"

# 清理所有暫存和構建文件
.PHONY: clean
clean: clean-dev clean-docs
	@echo "所有暫存和構建文件已清理"

# 清理開發暫存檔案
.PHONY: clean-dev
clean-dev:
	@echo "清理開發暫存檔案..."
	rm -rf __pycache__/
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf dist/
	rm -rf build/
	rm -rf *.egg-info/
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete

# 建置套件
.PHONY: build
build: clean-dev
	@echo "建置套件..."
	uv build

# 發布套件到 PyPI
.PHONY: publish
publish: build test
	@echo "發布套件到 PyPI..."
	uv run python scripts/publish.py

# === 複合指令 ===

# 完整的程式碼品質檢查
.PHONY: quality
quality: style check test
	@echo "程式碼品質檢查完成"

# 快速開發循環
.PHONY: dev
dev: style test
	@echo "開發循環完成"

# CI/CD 流程
.PHONY: ci
ci: check test coverage
	@echo "CI 流程完成"

# 完整檢查（發布前）
.PHONY: full-check
full-check: clean-dev dev-install quality coverage
	@echo "完整檢查完成"

# === 文檔工具 ===

# 構建 HTML 文檔
.PHONY: html
html:
	$(SPHINXBUILD) -b html "$(SOURCEDIR)" "$(BUILDDIR)/html" $(SPHINXOPTS)
	@echo ""
	@echo "HTML 文檔構建完成。文檔位置："
	@echo "  file://$(PWD)/$(BUILDDIR)/html/index.html"

# 清理文檔構建文件
.PHONY: clean-docs
clean-docs:
	rm -rf "$(BUILDDIR)"/*
	@echo "文檔構建文件已清理"

# 啟動本地服務器
.PHONY: serve
serve: html
	@echo "啟動文檔服務器於 http://localhost:8080"
	@cd "$(BUILDDIR)/html" && python -m http.server 8080

# 檢查連結
.PHONY: linkcheck
linkcheck:
	$(SPHINXBUILD) -b linkcheck "$(SOURCEDIR)" "$(BUILDDIR)/linkcheck" $(SPHINXOPTS)

# 構建所有文檔格式
.PHONY: all-docs
all-docs: clean-docs html
	@echo "所有文檔格式構建完成"

# 快速構建（不清理）
.PHONY: quick
quick:
	$(SPHINXBUILD) -b html "$(SOURCEDIR)" "$(BUILDDIR)/html" $(SPHINXOPTS)

# 實時監控和重建
.PHONY: livehtml
livehtml:
	sphinx-autobuild "$(SOURCEDIR)" "$(BUILDDIR)/html"
