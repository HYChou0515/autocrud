
from autocrud.cli.build import build_from_config

import typer
from pathlib import Path



if __name__ == "__main__":
    app_dir = Path(typer.get_app_dir("autocrud"))
    if not app_dir.exists():
        raise typer.Abort("請先使用 `autocrud-install <OPENAPI_URL>` 命令安裝資源模型。")
    build_from_config()
