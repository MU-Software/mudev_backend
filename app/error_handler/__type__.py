import typing

import fastapi
import fastapi.exceptions
import fastapi.responses
import starlette.requests

ExcType: typing.TypeAlias = typing.Type[Exception]
ReqType: typing.TypeAlias = starlette.requests.Request
RespType: typing.TypeAlias = fastapi.responses.JSONResponse
SyncErrHandlerType: typing.TypeAlias = typing.Callable[[ReqType, Exception], RespType]
AsyncErrHandlerType: typing.TypeAlias = typing.Callable[[ReqType, Exception], typing.Awaitable[RespType]]
ErrHandlerType: typing.TypeAlias = SyncErrHandlerType | AsyncErrHandlerType
ErrHandlersDef: typing.TypeAlias = dict[ExcType, ErrHandlerType]
