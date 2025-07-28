# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, os.path.abspath("../../"))

# 讀取 pyproject.toml 獲取項目信息
pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
with open(pyproject_path, "rb") as f:
    pyproject_data = tomllib.load(f)

project_info = pyproject_data["project"]

# 自動獲取版本號
try:
    import autocrud

    version = autocrud.__version__
    release = version
except ImportError as e:
    raise ImportError(f"無法導入 autocrud 模組來獲取版本號: {e}") from e
except AttributeError as e:
    raise AttributeError(f"autocrud 模組缺少 __version__ 屬性: {e}") from e

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

# 從 pyproject.toml 獲取項目信息
project = "AutoCRUD"  # 顯示名稱，保持美觀
author = ", ".join(author_info["name"] for author_info in project_info["authors"])
copyright = "2025, " + author

# 其他從 pyproject.toml 獲取的信息
project_description = project_info["description"]
project_license = project_info.get("license", {}).get("file", "LICENSE")
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
]

templates_path = ["_templates"]
exclude_patterns = []

language = "zh_TW"

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "furo"
html_static_path = ["_static"]

# -- Autodoc configuration ---------------------------------------------------
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "exclude-members": "__weakref__",
}

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

# -- Napoleon configuration --------------------------------------------------
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False

# -- Options for todo extension ----------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/todo.html#configuration

todo_include_todos = True
