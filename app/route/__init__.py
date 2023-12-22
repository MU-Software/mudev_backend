from __future__ import annotations

import pathlib as pt

import fastapi

import app.util.import_util as import_util


def get_routes() -> list[fastapi.APIRouter]:
    return import_util.auto_import_objs("router", "", pt.Path(__file__).parent)
