import contextlib
import importlib.util
import json
import pathlib as pt
import types
import typing

import app.util.mu_exception as mu_exception

safe_int: typing.Callable[[typing.Any], int] = mu_exception.ignore_exception(Exception, 0)(int)
safe_json_loads: typing.Callable[[typing.Any], dict | None] = mu_exception.ignore_exception(Exception, None)(json.loads)


def isiterable(a: typing.Any) -> bool:
    with contextlib.suppress(TypeError):
        return iter(a) is not None
    return False


def load_module(module_path: pt.Path) -> types.ModuleType:
    if not module_path.is_file():
        raise ValueError(f"module_path must be file path: {module_path}")

    module_path = module_path.resolve()
    module_name = module_path.stem
    module_spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module
