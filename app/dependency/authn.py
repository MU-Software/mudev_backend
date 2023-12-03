from __future__ import annotations

import typing
import uuid

import fastapi
import fastapi.security
import jwt
import redis

import app.const.cookie as cookie_const
import app.dependency.common as common_dep
import app.dependency.header as header_dep
import app.redis.key_type as redis_keytype
import app.schema.user as user_schema

oauth2_password_scheme = fastapi.security.OAuth2PasswordBearer(
    tokenUrl="/user/signin/",
)

oauth2_authorization_code_scheme = fastapi.security.OAuth2AuthorizationCodeBearer(
    authorizationUrl="/user/signin/",
    tokenUrl="/user/refresh/",
    refreshUrl="/user/refresh/",
)
TokenSchema = typing.TypeVar("TokenSchema", bound=user_schema.UserJWTToken)


def check_token_revocation(redis_session: redis.Redis, jti: str | uuid.UUID) -> None:
    redis_key: str = redis_keytype.RedisKeyType.TOKEN_REVOKED.as_redis_key(str(jti))
    if redis_session.get(name=redis_key):
        raise jwt.exceptions.InvalidTokenError("Token is revoked")


def get_access_token(
    redis_session: common_dep.redisDI,
    config_obj: common_dep.settingDI,
    request_user_agent: header_dep.user_agent,
    csrf_token: header_dep.csrf_token,
    authorization: typing.Annotated[str, fastapi.Depends(oauth2_password_scheme)],
) -> user_schema.AccessToken:
    token_obj = user_schema.AccessToken.from_token(
        token=authorization,
        key=config_obj.secret_key.get_secret_value() + csrf_token,
        request_user_agent=request_user_agent,
        config_obj=config_obj,
    )
    check_token_revocation(redis_session=redis_session, jti=token_obj.jti)
    return token_obj


def get_refresh_token(
    redis_session: common_dep.redisDI,
    config_obj: common_dep.settingDI,
    user_agent: header_dep.user_agent,
    refresh_token_cookie: typing.Annotated[str, cookie_const.CookieKey.REFRESH_TOKEN.as_cookie()],
) -> user_schema.RefreshToken:
    token_obj = user_schema.RefreshToken.from_token(
        token=refresh_token_cookie,
        key=config_obj.secret_key.get_secret_value(),
        request_user_agent=user_agent,
        config_obj=config_obj,
    )
    check_token_revocation(redis_session=redis_session, jti=token_obj.jti)
    return token_obj


access_token_di = typing.Annotated[user_schema.AccessToken, fastapi.Depends(get_access_token)]
refresh_token_di = typing.Annotated[user_schema.RefreshToken, fastapi.Depends(get_refresh_token)]
