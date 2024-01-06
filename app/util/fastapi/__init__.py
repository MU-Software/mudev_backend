import typing

import pydantic


class EmptyResponseSchema(pydantic.BaseModel):
    message: typing.Literal["ok"] = "ok"
