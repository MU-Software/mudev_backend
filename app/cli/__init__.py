import pathlib as pt
import typing

import typer

import app.util.mu_stdlib as utils

typer_app = typer.Typer()

current_dir = pt.Path(__file__).parent
for module_path in current_dir.glob("*.py"):
    if module_path.stem.startswith("__"):
        continue
    module = utils.load_module(module_path)

    cli_patterns: list[typing.Callable]
    if not utils.isiterable(cli_patterns := getattr(module, "cli_patterns", None)):
        continue

    for cli_func in cli_patterns:
        typer_app.command()(cli_func)
