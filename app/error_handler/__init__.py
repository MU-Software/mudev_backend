from __future__ import annotations

import pathlib as pt

import app.error_handler.__type__ as err_type
import app.util.import_util as import_util


def get_error_handlers() -> err_type.ErrHandlersDef:
    error_handler_collection: list[err_type.ErrHandlersDef] = import_util.auto_import_patterns(
        "error_handler_patterns",
        "err_",
        pt.Path(__file__).parent,
    )
    return {k: v for d in error_handler_collection for k, v in d.items()}
