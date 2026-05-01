from pathlib import Path

import typer

from specstar.cli import config
from specstar.cli.build import build_from_config

if __name__ == "__main__":
    app_dir = Path(typer.get_app_dir("specstar"))
    if not app_dir.exists():
        config.app()
    build_from_config()
