from __future__ import annotations

import pydantic_core

import app.const.error as error_const
import app.error_handler.__type__ as err_type


def exception_handler(req: err_type.ReqType, err: pydantic_core.ValidationError) -> err_type.RespType:
    return error_const.ServerError.UNKNOWN_SERVER_ERROR().response()


error_handler_patterns = {Exception: exception_handler}
