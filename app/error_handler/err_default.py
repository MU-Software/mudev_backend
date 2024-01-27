from __future__ import annotations

import json

import pydantic_core

import app.const.error as error_const
import app.error_handler.__type__ as err_type


def valueerror_handler(req: err_type.ReqType, err: ValueError) -> err_type.RespType:
    return error_const.ErrorStruct.from_exception(err).response()


def jsondecodeerror_handler(req: err_type.ReqType, err: json.JSONDecodeError) -> err_type.RespType:
    return error_const.ErrorStruct(
        type="json_decode_error",
        msg="이해할 수 없는 유형의 데이터를 받았어요.",
        input=err.doc,
        ctx={"pos": err.pos, "lineno": err.lineno, "colno": err.colno, "msg": err.msg},
    ).response()


def exception_handler(req: err_type.ReqType, err: pydantic_core.ValidationError) -> err_type.RespType:
    return error_const.ServerError.UNKNOWN_SERVER_ERROR().response()


error_handler_patterns = {
    ValueError: valueerror_handler,
    json.JSONDecodeError: jsondecodeerror_handler,
    Exception: exception_handler,
}
