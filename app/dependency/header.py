import typing

import fastapi

import app.const.cookie as cookie_const


def get_user_ip(
    request: fastapi.Request,
    real_ip: typing.Annotated[str | None, fastapi.Header(alias="X-Real-IP")] = None,
    forwarded_for: typing.Annotated[str | None, fastapi.Header(alias="X-Fowarded-For")] = None,
) -> str | None:
    return real_ip or forwarded_for or (request.client.host if request.client else None)


user_ip = typing.Annotated[str | None, fastapi.Depends(get_user_ip)]
user_agent = typing.Annotated[str | None, fastapi.Header(alias="User-Agent")]
csrf_token = typing.Annotated[str | None, fastapi.Cookie(alias=cookie_const.CookieKey.CSRF_TOKEN.name)]
