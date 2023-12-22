import pathlib as pt
import typing

import app.util.mu_stdlib as utils

T = typing.TypeVar("T")


def auto_import_objs(pattern_name: str, file_prefix: str, dir: pt.Path) -> list[T]:
    collected_objs: list[T] = []
    for module_path in dir.glob(f"**/{file_prefix}*.py"):
        if module_path.stem.startswith("__"):
            continue

        if obj := typing.cast(T, getattr(utils.load_module(module_path), pattern_name, None)):
            collected_objs.append(obj)
    return collected_objs


def auto_import_patterns(pattern_name: str, file_prefix: str, dir: pt.Path) -> list[T]:
    return list(filter(utils.isiterable, auto_import_objs(pattern_name, file_prefix, dir)))
