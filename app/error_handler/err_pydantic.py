from __future__ import annotations

import fastapi.responses
import pydantic_core

import app.error_handler.__type__ as err_type


def pydantic_validationerror_handler(req: err_type.ReqType, err: pydantic_core.ValidationError) -> err_type.RespType:
    status_code = fastapi.status.HTTP_422_UNPROCESSABLE_ENTITY
    content = err.errors(include_context=False)
    return fastapi.responses.JSONResponse(status_code=status_code, content=content)


error_handler_patterns = {pydantic_core.ValidationError: pydantic_validationerror_handler}
