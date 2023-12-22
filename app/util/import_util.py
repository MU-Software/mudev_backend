import pathlib as pt
import typing

import app.util.mu_stdlib as utils

T = typing.TypeVar("T")


def auto_import_patterns(pattern_prefix: str, file_prefix: str, dir: pt.Path) -> list[T]:
    collected_patterns: list[T] = []
    for module_path in dir.glob(f"{file_prefix}*.py"):
        if module_path.stem.startswith("__"):
            continue

        module = utils.load_module(module_path)
        pattern_name = f"{pattern_prefix}_patterns"
        if not utils.isiterable(patterns := typing.cast(T, getattr(module, pattern_name, None))):
            continue

        collected_patterns.append(patterns)
    return collected_patterns
