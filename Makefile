# AutoCRUD 文檔 Makefile

# 變數設定
SPHINXOPTS    ?=
SPHINXBUILD  ?= uv run sphinx-build
SOURCEDIR    = docs/source
BUILDDIR     = docs/build

# 默認目標
.PHONY: help
help:
	@echo "AutoCRUD 文檔構建工具"
	@echo ""
	@echo "可用的命令："
	@echo "  html       構建 HTML 文檔"
	@echo "  clean      清理構建文件"
	@echo "  serve      啟動本地文檔服務器"
	@echo "  linkcheck  檢查文檔中的連結"
	@echo "  test       運行文檔測試"

# 構建 HTML 文檔
.PHONY: html
html:
	$(SPHINXBUILD) -b html "$(SOURCEDIR)" "$(BUILDDIR)/html" $(SPHINXOPTS)
	@echo ""
	@echo "HTML 文檔構建完成。文檔位置："
	@echo "  file://$(PWD)/$(BUILDDIR)/html/index.html"

# 清理構建文件
.PHONY: clean
clean:
	rm -rf "$(BUILDDIR)"/*
	@echo "構建文件已清理"

# 啟動本地服務器
.PHONY: serve
serve: html
	@echo "啟動文檔服務器於 http://localhost:8080"
	@cd "$(BUILDDIR)/html" && python -m http.server 8080

# 檢查連結
.PHONY: linkcheck
linkcheck:
	$(SPHINXBUILD) -b linkcheck "$(SOURCEDIR)" "$(BUILDDIR)/linkcheck" $(SPHINXOPTS)

# 構建所有格式
.PHONY: all
all: clean html
	@echo "所有文檔格式構建完成"

# 快速構建（不清理）
.PHONY: quick
quick:
	$(SPHINXBUILD) -b html "$(SOURCEDIR)" "$(BUILDDIR)/html" $(SPHINXOPTS)

# 實時監控和重建
.PHONY: livehtml
livehtml:
	sphinx-autobuild "$(SOURCEDIR)" "$(BUILDDIR)/html"
