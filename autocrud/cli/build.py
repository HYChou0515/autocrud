from msgspec import UNSET, Struct, UnsetType, convert
import msgspec
from pydantic import BaseModel
import sys
from datetime import datetime
from tenacity import retry, wait_fixed, stop_after_attempt
from typer import Typer
import typer
import json
from pathlib import Path
import importlib.util
import typing
from typing import Annotated, Literal
from rich import print_json, print
from rich.prompt import Prompt
import fstui
import httpx
from autocrud.cli import config
from autocrud.types import ResourceMeta, RevisionInfo
from rich.table import Table
from rich.console import Console
from rich.text import Text


def build_from_config():
    app_dir = Path(typer.get_app_dir("autocrud"))
    with (app_dir / "resources.json").open("rb") as f:
        resource_map = json.load(f)
    with (Path(app_dir) / "config.json").open("rb") as f:
        user_config = config.UserConfig.model_validate_json(f.read())
    module_name = "autocrud_cli_models"
    spec = importlib.util.spec_from_file_location(module_name, app_dir / "model.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    for name in dir(module):
        if not name.startswith("_"):
            globals()[name] = getattr(module, name)

    app = Typer()
    for name, type_name in resource_map.items():
        model: type[BaseModel] = getattr(module, type_name)
        ui = ResourceUI(user_config, model, name)
        cmd = Typer()

        cmd.command(name="create")(ui.create)
        cmd.command(name="list")(ui.list_objects)
        app.add_typer(cmd, name=name)
    app()


class BasicChoice(Struct):
    value: typing.Any
    label: str | UnsetType = UNSET
    abbr: str | UnsetType = UNSET


class IntChoice(Struct):
    value: int
    prefix: str = ""
    group_name: str | UnsetType = UNSET


Choice = typing.Union[BasicChoice, IntChoice]


def ui_choice(choices: list[Choice]) -> Choice:
    choice_map: dict[str, Choice] = {}
    groups: dict[str, list[IntChoice]] = {}
    choice_labels: list[str | list[IntChoice]] = []
    for choice in choices:
        if isinstance(choice, IntChoice):
            if choice.group_name is UNSET:
                choice_labels.append(f"{choice.prefix}{choice.value}")
            else:
                if choice.group_name not in groups:
                    groups[choice.group_name] = []
                    choice_labels.append(groups[choice.group_name])
                groups[choice.group_name].append(choice)
            choice_map[f"{choice.prefix}{choice.value}"] = choice
        elif isinstance(choice, BasicChoice):
            if choice.abbr is not UNSET:
                choice_map[choice.abbr] = choice
            elif choice.label is not UNSET:
                choice_map[choice.label] = choice
            else:
                choice_map[str(choice.value)] = choice
            if choice.label is not UNSET:
                choice_labels.append(choice.label)
            else:
                choice_labels.append(str(choice.value))
        else:
            raise ValueError("Unknown choice type: {}".format(type(choice)))

    for i in range(len(choice_labels)):
        if isinstance(cs := choice_labels[i], list):
            minv, maxv = min(c.value for c in cs), max(c.value for c in cs)
            if minv == maxv:
                choice_labels[i] = f"{cs[0].group_name} ({cs[0].prefix}{minv})"
            else:
                choice_labels[i] = (
                    f"{cs[0].group_name} ({cs[0].prefix}{minv}-{cs[0].prefix}{maxv})"
                )

    while True:
        selection = Prompt.ask("/".join(choice_labels))
        if selection in choice_map:
            return choice_map[selection]
        print("Please select a valid option.")


class ReturnType(Struct):
    data: dict
    revision_info: RevisionInfo
    meta: ResourceMeta


def format_time(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_table_cell(value: typing.Any) -> Text:
    if isinstance(value, datetime):
        return Text(format_time(value))
    if value is None:
        text = Text("<null>")
        text.stylize("grey39 italic")
        print(text)
        return text
    if isinstance(value, int):
        text = Text(str(value))
        text.stylize("cyan")
        return text
    value = str(value)
    if value == "":
        text = Text("<empty>")
        text.stylize("grey39 italic")
        return text
    return Text(value)


def print_table(title: str, columns: list[str], rows: list[list[typing.Any]]):
    table = Table(title=title)
    for col in columns:
        table.add_column(col)
    for row in rows:
        table.add_row(*[format_table_cell(item) for item in row])
    console = Console()
    console.print(table)


class ResourceUI:
    def __init__(
        self, user_config: config.UserConfig, model: type[BaseModel], name: str
    ):
        self.user_config = user_config
        self.model = model
        self.name = name
        self.retry_get = retry(
            wait=wait_fixed(2),
            stop=stop_after_attempt(5),
        )

    def create(self):
        obj = fstui.create(
            self.model, title=f"Create new {self.name}", default_values={}
        )
        if obj is None:
            raise typer.Exit("Creation cancelled.")
        print_json(obj.model_dump_json(indent=2))
        resp = httpx.post(
            f"{self.user_config.autocrud_url}/{self.name}",
            json=json.loads(obj.model_dump_json()),
        )
        resp.raise_for_status()
        print_json(resp.text)

    def page_objects(
        self,
        page_size: int,
        page_index: int,
        show_type: Literal["meta", "data"] = "data",
    ) -> None:
        resp = self.retry_get(httpx.get)(
            f"{self.user_config.autocrud_url}/{self.name}/full",
            params={"limit": page_size + 1, "offset": page_index * page_size},
        )
        objs = resp.json()
        has_prev = page_index > 0
        has_next = len(objs) == page_size + 1
        objs = convert(objs[:page_size], typing.List[ReturnType])

        if show_type == "data":
            print_table(
                title=f"{self.name}",
                columns=["Index"] + list(self.model.model_fields.keys()),
                rows=[
                    [i + 1 + page_size * page_index]
                    + [obj.data.get(field) for field in self.model.model_fields.keys()]
                    for i, obj in enumerate(objs)
                ],
            )
        else:
            print_table(
                title=f"{self.name}",
                columns=[
                    "Index",
                    "id",
                    "revision",
                    "schema",
                    "created",
                    "updated",
                ],
                rows=[
                    [
                        i + 1 + page_size * page_index,
                        obj.revision_info.resource_id,
                        obj.revision_info.revision_id,
                        obj.revision_info.schema_version,
                        f"{obj.revision_info.created_by} ({format_time(obj.revision_info.created_time)})",
                        f"{obj.revision_info.updated_by} ({format_time(obj.revision_info.updated_time)})",
                    ]
                    for i, obj in enumerate(objs)
                ],
            )
        choices = [
            IntChoice(i + 1 + page_size * page_index, group_name="Show")
            for i in range(len(objs))
        ]
        if show_type == "data":
            choices.append(BasicChoice("meta", label="[M]eta View", abbr="m"))
        else:
            choices.append(BasicChoice("data", label="[D]ata View", abbr="d"))
        if has_prev:
            choices.append(BasicChoice("prev", label="[P]revious Page", abbr="p"))
        if has_next:
            choices.append(BasicChoice("next", label="[N]ext Page", abbr="n"))

        choices.append(BasicChoice("quit", label="[Q]uit", abbr="q"))
        action = ui_choice(choices)
        if action.value == "quit":
            return
        if action.value == "prev":
            return self.page_objects(page_size, page_index - 1, show_type=show_type)
        if action.value == "next":
            return self.page_objects(page_size, page_index + 1, show_type=show_type)
        if action.value == "data":
            return self.page_objects(page_size, page_index, show_type="data")
        if action.value == "meta":
            return self.page_objects(page_size, page_index, show_type="meta")
        show_index = (int(action.value) - 1) % page_size
        selected_obj = objs[show_index]
        print_json(msgspec.json.encode(selected_obj).decode("utf-8"))
        return self.page_objects(page_size, page_index, show_type=show_type)

    def list_objects(
        self, page_size: Annotated[int, typer.Option("-p", help="Page size")] = 5
    ):
        self.page_objects(page_size, 0)
