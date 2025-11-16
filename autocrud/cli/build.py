from msgspec import UNSET, Struct, UnsetType, convert, to_builtins
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
from rich import print
from rich.prompt import Prompt
import fstui
import httpx
from autocrud.cli import config
from autocrud.types import ResourceMeta, ResourceMetaSortKey, RevisionInfo
from rich.table import Table
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
        cmd.command(name="update")(ui.ui_paged(ui.update))
        cmd.command(name="delete")(ui.ui_paged(ui.delete))
        cmd.command(name="list")(ui.ui_paged(ui.list_objects))
        cmd.callback(invoke_without_command=True)(ui.callback)

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


class EmptyCell:
    pass


EMPTY_CELL = EmptyCell()


def format_table_cell(value: typing.Any) -> Text:
    if isinstance(value, Text):
        return value
    if value is EMPTY_CELL:
        return Text("")
    if isinstance(value, datetime):
        return Text(format_time(value))
    if value is None:
        text = Text("<null>")
        text.stylize("grey39 italic")
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


def print_table(
    title: str | None,
    columns: list[str] | None,
    rows: list[list[typing.Any] | EmptyCell],
):
    table = Table(title=title, show_header=columns is not None)
    if columns is not None:
        for col in columns:
            table.add_column(col)
    for row in rows:
        if row is EMPTY_CELL:
            table.add_section()
        else:
            table.add_row(*[format_table_cell(item) for item in row])
    print(table)


def print_object(obj: dict | Struct):
    rows = []

    def to_rows(obj: dict | Struct, indent: int):
        if isinstance(obj, Struct):
            obj = to_builtins(obj)
        for k in obj.keys():
            if isinstance(obj[k], (dict, Struct)):
                rows.append([EMPTY_CELL] * indent + [k, EMPTY_CELL])
                to_rows(obj[k], indent + 1)
                rows.append(EMPTY_CELL)
            else:
                rows.append([EMPTY_CELL] * indent + [k, format_table_cell(obj[k])])

    to_rows(obj, 0)
    print_table(
        title=None,
        columns=None,
        rows=rows,
    )


class PageOptions(Struct):
    page_size: int = 5
    page_index: int = 0
    sort_by: tuple[str] = ("-updated_time",)
    show_type: Literal["meta", "data"] = "data"
    mode: Literal["view", "select"] = "view"


class ResourceUI:
    def __init__(
        self, user_config: config.UserConfig, model: type[BaseModel], name: str
    ):
        self.user_config = user_config
        self.model = model
        self.name = name
        self.retry = retry(
            wait=wait_fixed(2),
            stop=stop_after_attempt(5),
        )

    @staticmethod
    def ui_paged(func):
        def wrapper(
            page_size: Annotated[int, typer.Option("-p", help="Page size")] = 5,
            sort_by: Annotated[list[str], typer.Option("-s", help="Sort by field")] = [
                "-updated_time"
            ],
        ):
            page = PageOptions(page_size=page_size, sort_by=sort_by)
            return func(page)

        return wrapper

    def create(self):
        obj = fstui.create(
            self.model, title=f"Create new {self.name}", default_values={}
        )
        if obj is None:
            raise typer.Exit("Creation cancelled.")
        resp = httpx.post(
            f"{self.user_config.autocrud_url}/{self.name}",
            json=json.loads(obj.model_dump_json()),
        )
        resp.raise_for_status()
        resource_id = resp.json()["resource_id"]
        resp = self.retry(httpx.get)(
            f"{self.user_config.autocrud_url}/{self.name}/{resource_id}/full",
        )
        resp.raise_for_status()
        print_object(resp.json())

    def select_object(self, page: PageOptions):
        while True:
            obj = self.page_objects(page)
            if obj is None:
                break
            yield obj

    def select_one_object(self, page: PageOptions):
        obj = None
        for obj in self.select_object(page):
            break
        if not obj:
            raise typer.Exit("No object selected.")
        return obj

    def update(self, page: PageOptions):
        obj = self.select_one_object(page)
        new_data = fstui.create(
            self.model, title=f"Update {self.name}", default_values=obj.data
        )
        resp = httpx.put(
            f"{self.user_config.autocrud_url}/{self.name}/{obj.meta.resource_id}",
            json=json.loads(new_data.model_dump_json()),
        )
        resp.raise_for_status()
        print_object(resp.json())

    def page_objects(
        self,
        page: PageOptions,
    ) -> ReturnType | None:
        sorts = []
        for sort_field in page.sort_by:
            direction = "+"
            key = sort_field
            if sort_field.startswith("-"):
                direction = "-"
                key = sort_field[1:]
            elif sort_field.startswith("+"):
                key = sort_field[1:]
            if key in ResourceMetaSortKey:
                sorts.append(dict(type="meta", key=key, direction=direction))
            else:
                sorts.append(dict(type="data", field_path=key, direction=direction))
        resp = self.retry(httpx.get)(
            f"{self.user_config.autocrud_url}/{self.name}/full",
            params={
                "limit": page.page_size + 1,
                "offset": page.page_index * page.page_size,
                "sorts": msgspec.json.encode(sorts).decode("utf-8"),
            },
        )
        resp.raise_for_status()
        objs = resp.json()
        has_prev = page.page_index > 0
        has_next = len(objs) == page.page_size + 1
        objs = convert(objs[: page.page_size], typing.List[ReturnType])

        if page.show_type == "data":
            print_table(
                title=f"{self.name}",
                columns=["Index"] + list(self.model.model_fields.keys()),
                rows=[
                    [i + 1 + page.page_size * page.page_index]
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
                        i + 1 + page.page_size * page.page_index,
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
            IntChoice(i + 1 + page.page_size * page.page_index, group_name="Show")
            for i in range(len(objs))
        ]
        if page.show_type == "data":
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
            return None
        elif action.value == "prev":
            page.page_index -= 1
        elif action.value == "next":
            page.page_index += 1
        elif action.value == "data":
            page.show_type = "data"
        elif action.value == "meta":
            page.show_type = "meta"
        else:
            show_index = (int(action.value) - 1) % page.page_size
            selected_obj = objs[show_index]
            return selected_obj
        return self.page_objects(page)

    def list_objects(self, page: PageOptions):
        for obj in self.select_object(page):
            print_object(obj)

    def delete(self, page: PageOptions):
        obj = self.select_one_object(page)
        print_object(obj)

        ans = Prompt.ask(
            f"Are you sure to delete {self.name} {obj.meta.resource_id}? Type 'yes' to confirm",
            default="no",
            choices=["yes", "no"],
        )
        if ans.lower() != "yes":
            raise typer.Exit("Deletion cancelled.")

        ans = Prompt.ask(
            "This action is irreversible. Type the revision ID to confirm",
        )
        if ans != obj.revision_info.revision_id:
            raise typer.Exit("Revision ID not matched. Deletion cancelled.")

        resp = self.retry(httpx.delete)(
            f"{self.user_config.autocrud_url}/{self.name}/{obj.meta.resource_id}",
        )
        print_object(resp.json())
        print(f"[red]Deleted {self.name} {obj.meta.resource_id}[/red]")

    def callback(
        self,
        ctx: typer.Context,
    ):
        if ctx.invoked_subcommand is None:
            return self.list_objects(PageOptions())
