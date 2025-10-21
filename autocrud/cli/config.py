from contextlib import suppress
from typer import Typer
import typer
import subprocess as sp
import json
import httpx
from pathlib import Path
app = Typer()

@app.command()
def install(url: str):
    app_dir = Path(typer.get_app_dir("autocrud"))
    app_dir.mkdir(parents=True, exist_ok=True)
    
    resp = httpx.get(url)
    json_data = resp.json()
    resource_names = {}
    for path, methods in json_data['paths'].items():
        component = None
        with suppress(KeyError):
            component = methods['post']['requestBody']['content']['application/json']['schema']['$ref']
        if component:
            resource_names[path.rsplit("/", 1)[-1]] = component.rsplit("/", 1)[-1]
    with (Path(app_dir) / "resources.json").open("w") as f:
        json.dump(resource_names, f, indent=4)
    sp.run(["datamodel-codegen", "--url", url, "--input-file-type", "openapi", "--output", Path(app_dir)/"model.py"])

if __name__ == "__main__":
    install("http://localhost:8000/openapi.json")
