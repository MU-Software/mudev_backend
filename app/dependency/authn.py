from __future__ import annotations

import typing
import uuid

import fastapi
import fastapi.security
import jwt
import pydantic
import redis

import app.config.fastapi as fastapi_config
import app.const.cookie as cookie_const
import app.dependency.common as common_dep
import app.dependency.header as header_dep
import app.redis.key_type as redis_keytype
import app.schema.user as user_schema

oauth2_password_scheme = fastapi.security.OAuth2PasswordBearer(
    tokenUrl="/user/signin/",
    auto_error=False,
)

# oauth2_authorization_code_scheme = fastapi.security.OAuth2AuthorizationCodeBearer(
#     authorizationUrl="/user/signin/",
#     tokenUrl="/user/refresh/",
#     refreshUrl="/user/refresh/",
# )


TokenType = typing.TypeVar("TokenType", bound=user_schema.UserJWTToken)


def check_token_revocation(redis_session: redis.Redis, jti: str | uuid.UUID) -> None:
    redis_key: str = redis_keytype.RedisKeyType.TOKEN_REVOKED.as_redis_key(str(jti))
    if redis_session.get(name=redis_key):
        raise jwt.exceptions.InvalidTokenError("Token is revoked")


def parse_token(
    parser_cls: type[TokenType],
    token: str,
    key: str,
    ua: str,
    config_obj: fastapi_config.FastAPISetting,
    redis_session: redis.Redis,
) -> TokenType:
    try:
        token_obj = parser_cls.from_token(token=token, key=key, request_user_agent=ua, config_obj=config_obj)
        check_token_revocation(redis_session=redis_session, jti=token_obj.jti)
        return token_obj
    except pydantic.ValidationError as err:
        raise jwt.exceptions.InvalidTokenError("Token data is invalid") from err
    except jwt.exceptions.PyJWTError as err:
        raise err
    except Exception as err:
        raise jwt.exceptions.InvalidTokenError("Token is invalid") from err


def get_access_token_or_none(
    redis_session: common_dep.redisDI,
    config_obj: common_dep.settingDI,
    user_agent: header_dep.user_agent = None,
    csrf_token: header_dep.csrf_token = None,
    authorization: typing.Annotated[str | None, fastapi.Depends(oauth2_password_scheme)] = None,
) -> user_schema.AccessToken | None:
    return (
        parse_token(
            parser_cls=user_schema.AccessToken,
            token=authorization,
            key=config_obj.secret_key.get_secret_value() + csrf_token,
            ua=user_agent,
            config_obj=config_obj,
            redis_session=redis_session,
        )
        if all([user_agent, csrf_token, authorization])
        else None
    )


access_token_or_none_di = typing.Annotated[user_schema.AccessToken | None, fastapi.Depends(get_access_token_or_none)]


def get_access_token(access_token_or_none_di: access_token_or_none_di = None) -> user_schema.AccessToken:
    if not access_token_or_none_di:
        raise jwt.exceptions.InvalidTokenError("Token is not provided")

    return access_token_or_none_di


access_token_di = typing.Annotated[user_schema.AccessToken, fastapi.Depends(get_access_token)]


def get_refresh_token(
    redis_session: common_dep.redisDI,
    config_obj: common_dep.settingDI,
    ua: header_dep.user_agent = None,
    refresh_token: typing.Annotated[str | None, cookie_const.CookieKey.REFRESH_TOKEN.as_cookie()] = None,
) -> user_schema.RefreshToken:
    if not all([ua, refresh_token]):
        raise jwt.exceptions.InvalidTokenError("User-Agent or Token is not provided")

    return parse_token(
        parser_cls=user_schema.RefreshToken,
        token=refresh_token,
        key=config_obj.secret_key.get_secret_value(),
        ua=ua,
        config_obj=config_obj,
        redis_session=redis_session,
    )


refresh_token_di = typing.Annotated[user_schema.RefreshToken, fastapi.Depends(get_refresh_token)]
