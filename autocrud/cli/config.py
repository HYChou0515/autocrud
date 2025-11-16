from contextlib import suppress
from pydantic import BaseModel
from typer import Typer
import typer
import subprocess as sp
import json
import httpx
from pathlib import Path


class UserConfig(BaseModel):
    autocrud_url: str
    openapi_url: str


app = Typer(
    invoke_without_command=True,
)


@app.callback()
def install(ctx: typer.Context):
    url = typer.prompt("請輸入 API 的 base URL")
    openapi_url = typer.prompt(
        "請輸入 OpenAPI 文件的 URL", default=f"{url}/openapi.json"
    )
    autocrud_url = typer.prompt("請輸入 Autocrud 的 URL", default=f"{url}")
    app_dir = Path(typer.get_app_dir("autocrud"))
    app_dir.mkdir(parents=True, exist_ok=True)

    resp = httpx.get(openapi_url)
    json_data = resp.json()
    resource_names: dict[str, str] = {}
    for path, methods in json_data["paths"].items():
        component = None
        with suppress(KeyError):
            component = methods["post"]["requestBody"]["content"]["application/json"][
                "schema"
            ]["$ref"]
        if component:
            resource_names[path.rsplit("/", 1)[-1]] = component.rsplit("/", 1)[-1]
    with (Path(app_dir) / "resources.json").open("w") as f:
        json.dump(resource_names, f, indent=4)
    with (Path(app_dir) / "config.json").open("w") as f:
        f.write(
            UserConfig(
                autocrud_url=autocrud_url, openapi_url=openapi_url
            ).model_dump_json(indent=4)
        )
    sp.run(
        [
            "datamodel-codegen",
            "--url",
            openapi_url,
            "--input-file-type",
            "openapi",
            "--output",
            Path(app_dir) / "model.py",
        ]
    )


if __name__ == "__main__":
    install("http://localhost:8000/openapi.json")
