from __future__ import annotations

import jwt.exceptions

import app.const.error as error_const
import app.error_handler.__type__ as err_type


def jwt_error_handler(req: err_type.ReqType, err: jwt.exceptions.PyJWTError) -> err_type.RespType:
    return error_const.AuthNError.INVALID_ACCESS_TOKEN().response()


error_handler_patterns = {jwt.exceptions.PyJWTError: jwt_error_handler}
