from __future__ import annotations

import fastapi.responses
import jwt.exceptions

import app.const.error as error_const
import app.error_handler.__type__ as err_type


def jwt_error_handler(req: err_type.ReqType, err: jwt.exceptions.PyJWTError) -> err_type.RespType:
    status_code = fastapi.status.HTTP_401_UNAUTHORIZED
    content = error_const.AuthError.INVALID_ACCESS_TOKEN().model_dump()
    return fastapi.responses.JSONResponse(status_code=status_code, content=content)


error_handler_patterns = {jwt.exceptions.PyJWTError: jwt_error_handler}
