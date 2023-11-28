import typing

import fastapi

import app.const.cookie as cookie_const
import app.const.header as header_const


def get_user_ip(
    request: fastapi.Request,
    real_ip: typing.Annotated[str | None, header_const.HeaderKey.REAL_IP.as_dependency()] = None,
    forwarded_for: typing.Annotated[str | None, header_const.HeaderKey.FORWARDED_FOR.as_dependency()] = None,
) -> str | None:
    return real_ip or forwarded_for or (request.client.host if request.client else None)


user_ip = typing.Annotated[str | None, fastapi.Depends(get_user_ip)]
user_agent = typing.Annotated[str | None, header_const.HeaderKey.USER_AGENT.as_dependency()]
csrf_token = typing.Annotated[str | None, cookie_const.CookieKey.CSRF_TOKEN.as_dependency()]
