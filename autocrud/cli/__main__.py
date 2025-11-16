from autocrud.cli.build import build_from_config

import typer
from pathlib import Path
from autocrud.cli import config

if __name__ == "__main__":
    app_dir = Path(typer.get_app_dir("autocrud"))
    if not app_dir.exists():
        config.app()
    build_from_config()
