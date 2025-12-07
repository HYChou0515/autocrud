# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath("../../"))

# 嘗試讀取 pyproject.toml 獲取項目信息
try:
    # Python 3.11+ 內建支持
    import tomllib

    pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        pyproject_data = tomllib.load(f)
    project_info = pyproject_data.get("project", {})
except (ImportError, FileNotFoundError):
    # 如果找不到 tomllib 或 pyproject.toml，使用默認值
    project_info = {
        "name": "AutoCRUD",
        "description": "自動生成 CRUD API 的 Python 庫",
        "authors": [{"name": "HYChou", "email": "hychou0515@gmail.com"}],
        "keywords": ["crud", "api", "fastapi", "msgspec"],
    }

# 自動獲取版本號
try:
    # 嘗試從已安裝的包獲取版本
    import autocrud

    version = getattr(autocrud, "__version__", "dev")
    release = version
except ImportError:
    # 如果包沒有安裝，嘗試從 pyproject.toml 獲取
    try:
        version = project_info.get("version", "dev")
        release = version
    except Exception:
        version = "dev"
        release = "dev"

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

# 從 pyproject.toml 獲取項目信息
project = "AutoCRUD"  # 顯示名稱，保持美觀
author = ", ".join(
    author_info.get("name", "Unknown")
    for author_info in project_info.get("authors", [])
)
copyright = "2025, " + author

# 其他從 pyproject.toml 獲取的信息
project_description = project_info.get("description", "自動生成 CRUD API 的 Python 庫")
project_license = "MIT"
project_keywords = ", ".join(project_info.get("keywords", []))

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.todo",
    "sphinx.ext.coverage",
    "sphinx.ext.imgmath",
    "sphinx.ext.mathjax",
    "sphinx.ext.ifconfig",
    "sphinx.ext.githubpages",
    "sphinx.ext.napoleon",
    "sphinx_autodoc_typehints",
    "myst_parser",
    "sphinx_design",  # 添加網格和卡片支持
    "sphinx_termynal",
]

templates_path = ["_templates"]
exclude_patterns = []
language = "zh_TW"

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "furo"
html_static_path = ["_static"]

# Furo 主題配置
html_theme_options = {
    "sidebar_hide_name": False,
    "light_css_variables": {
        "color-brand-primary": "#2563eb",
        "color-brand-content": "#2563eb",
    },
    "dark_css_variables": {
        "color-brand-primary": "#60a5fa",
        "color-brand-content": "#60a5fa",
    },
    "source_repository": "https://github.com/HYChou0515/autocrud/",
    "source_branch": "master",
    "source_directory": "docs/source/",
}

html_title = f"{project} 文檔"
html_short_title = project
html_favicon = None  # 可以添加 favicon 路徑

# 添加自定義 CSS 和 JS
html_css_files = ["custom.css"]
# html_js_files = ["custom.js"]

# -- Autodoc configuration ---------------------------------------------------
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "exclude-members": "__weakref__",
}

autodoc_typehints = "description"
autodoc_typehints_description_target = "documented"

# -- MyST configuration ------------------------------------------------------
myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "dollarmath",
    "fieldlist",
    "html_admonition",
    "html_image",
    "linkify",
    "replacements",
    "smartquotes",
    "strikethrough",
    "substitution",
    "tasklist",
]

myst_heading_anchors = 3
myst_fence_as_directive = ["mermaid"]

# -- Napoleon configuration --------------------------------------------------
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False

# -- Options for todo extension ----------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/todo.html#configuration

todo_include_todos = True

# -- Options for internationalization ----------------------------------------
locale_dirs = ["locale/"]  # 多語言支持路徑
gettext_compact = False

# -- Custom configuration ----------------------------------------------------

# 設置 GitHub 相關信息
html_context = {
    "github_user": "HYChou0515",
    "github_repo": "autocrud",
    "github_version": "master",
    "doc_path": "docs/source",
    "display_github": True,
}

# 添加項目相關信息到模板上下文
html_context.update(
    {
        "project_description": project_description,
        "project_keywords": project_keywords,
        "project_license": project_license,
    },
)

# OpenGraph 和社交媒體元標籤
html_theme_options.update(
    {
        "announcement": None,  # 可以添加公告
    },
)

# 如果有 _static 目錄中的自定義文件，取消注釋以下行
# html_logo = "_static/logo.png"
# html_favicon = "_static/favicon.ico"

# 自定義側邊欄
html_sidebars = {
    "**": [
        "sidebar/scroll-start.html",
        "sidebar/brand.html",
        "sidebar/search.html",
        "sidebar/navigation.html",
        "sidebar/ethical-ads.html",
        "sidebar/scroll-end.html",
    ],
}

# 禁用某些警告
suppress_warnings = [
    "myst.header",  # 禁用 MyST 標題警告
]

# 添加外部鏈接檢查（可選）
linkcheck_ignore = [
    r"http://localhost:\d+/",  # 忽略本地鏈接
]

# 設置默認角色
default_role = "code"

# 添加 GitHub Pages 支持
if os.environ.get("GITHUB_ACTIONS"):
    html_baseurl = "https://hychou0515.github.io/autocrud/"
