
from pydantic import BaseModel
import sys
from pydantic_core import *
from typer import Typer
import typer
import json
from pathlib import Path
import importlib.util
from pydantic import *
import makefun
import typing
import inspect

def get_type_string(annotation):
    """Convert a type annotation to a string representation for makefun."""
    # Handle Optional types (Union with None)
    origin = typing.get_origin(annotation)
    if origin is typing.Union:
        args = typing.get_args(annotation)
        # Check if it's Optional (Union[T, None])
        if len(args) == 2 and type(None) in args:
            inner_type = args[0] if args[1] is type(None) else args[1]
            return f"typing.Optional[{get_type_string(inner_type)}]"
    
    # Handle other generic types
    if origin is not None:
        args = typing.get_args(annotation)
        if args:
            args_str = ", ".join(get_type_string(arg) for arg in args)
            origin_name = getattr(origin, '__name__', str(origin))
            return f"{origin_name}[{args_str}]"
    
    # Handle simple types
    if hasattr(annotation, '__name__'):
        return annotation.__name__
    
    # Fallback to string representation
    return str(annotation)

def model_command(app: Typer, model: type[BaseModel]):
    def decorator(func):
        # wrapper 本體

        # 生成簽名字串
        param_strs = []
        for name, field in model.model_fields.items():
            anno = field.annotation
            help_text = getattr(field, "description", None)

            # default 處理
            if (field.default is ... or field.default is PydanticUndefined) and field.default_factory is None:
                default = "..."
            elif field.default_factory is not None:
                default = repr(field.default_factory())
            else:
                default = repr(field.default)

            # Use the actual annotation object, not a string
            type_str = get_type_string(anno)
            param_str = f"{name}: {type_str} = typer.Option({default}, help={repr(help_text)})"
            param_strs.append(param_str)
        signature_str = ", ".join(param_strs)

        # Create a namespace with necessary types for evaluation
        eval_namespace = {
            'typer': typer,
            'typing': typing,
            **{name: getattr(typing, name) for name in dir(typing) if not name.startswith('_')},
        }
        
        # Add model-specific types to namespace
        for field_name, field in model.model_fields.items():
            anno = field.annotation
            # Add the actual type to namespace if it has a name
            if hasattr(anno, '__name__'):
                eval_namespace[anno.__name__] = anno
            # Handle Optional and other generic types - extract inner types
            origin = typing.get_origin(anno)
            if origin is typing.Union:
                for arg in typing.get_args(anno):
                    if arg is not type(None) and hasattr(arg, '__name__'):
                        eval_namespace[arg.__name__] = arg

        # 用 makefun.with_signature 生成帶簽名函數
        @makefun.with_signature(f"create({signature_str})", func_name="create", module_name=None, eval_local_ns=eval_namespace)
        def create(**kwargs):
            obj = model(**kwargs)
            return func(obj)

        return app.command()(create)
    return decorator

def build_from_config():
    app_dir = Path(typer.get_app_dir("autocrud"))
    with (app_dir / "resources.json").open() as f:
        resource_map = json.load(f)
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
        model = getattr(module, type_name)
        cmd = Typer()
        @model_command(cmd, model)
        def create_model(obj: BaseModel):
            print(obj.model_dump_json())

        app.add_typer(cmd, name=name)
    app()
