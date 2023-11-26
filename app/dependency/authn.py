from __future__ import annotations

import functools
import typing

import fastapi
import jwt
import pydantic

import app.const.cookie as cookie_const
import app.crud.user as user_crud
import app.db.model.user as user_model
import app.dependency.common as common_dep
import app.dependency.header as header_dep
import app.redis.key_type as redis_keytype
import app.schema.user as user_schema
import app.util.fastapi.cookie as cookie_util


class AccessTokenDI(pydantic.BaseModel):
    setting: common_dep.settingDI
    db_session: common_dep.dbDI
    redis_session: common_dep.redisDI
    user_agent: header_dep.user_agent
    csrf_token: header_dep.csrf_token
    authorization: typing.Annotated[str, fastapi.Header("Authorization")]

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    @functools.cached_property
    def token_obj(self) -> user_schema.AccessToken:
        return user_schema.AccessToken.from_token(
            token=self.authorization.replace("Bearer ", ""),
            key=self.setting.secret_key.get_secret_value() + self.csrf_token,
            request_ua=self.user_agent,
        )

    @functools.cached_property
    def user(self) -> user_model.User:
        return user_crud.userCRUD.get(self.db_session, self.token_obj.user)

    @pydantic.model_validator(mode="after")
    def validate_model(self) -> typing.Self:
        # Check token revocation
        redis_key: str = redis_keytype.RedisKeyType.TOKEN_REVOKED.as_redis_key(str(self.token_obj.jti))
        if self.redis_session.get(name=redis_key):
            raise jwt.exceptions.InvalidTokenError("Token is revoked")

        return self


class OptionalAccessTokenDI(AccessTokenDI):
    authorization: typing.Annotated[str | None, fastapi.Header("Authorization")] = None

    @functools.cached_property
    def token_obj(self) -> user_schema.AccessToken | None:
        return super().token_obj if self.authorization else None

    @functools.cached_property
    def user(self) -> user_model.User | None:
        return super().user if self.authorization else None


class RefreshTokenDI(pydantic.BaseModel):
    setting: common_dep.settingDI
    db_session: common_dep.dbDI
    redis_session: common_dep.redisDI
    user_agent: header_dep.user_agent
    csrf_token: header_dep.csrf_token
    refresh_token: typing.Annotated[str, fastapi.Cookie]

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    @functools.cached_property
    def signin_history(self) -> user_model.UserSignInHistory:
        return user_crud.userSignInHistoryCRUD.get(self.db_session, self.token_obj.jti)

    @functools.cached_property
    def user(self) -> user_model.User:
        return user_crud.userCRUD.get(self.db_session, self.token_obj.user)

    @property
    def cookie(self) -> cookie_util.Cookie:
        return cookie_util.Cookie(
            key=cookie_const.CookieKey.REFRESH_TOKEN.value,
            value=self.refresh_token,
            expires=self.token_obj.exp,
            **self.setting.to_cookie_config(),
        )

    @functools.cached_property
    def token_obj(self) -> user_schema.RefreshToken:
        return user_schema.RefreshToken.from_token(
            token=self.refresh_token,
            key=self.setting.secret_key.get_secret_value(),
            request_ua=self.user_agent,
        )

    @pydantic.model_validator(mode="after")
    def validate_model(self) -> typing.Self:
        # Check token revocation
        redis_key: str = redis_keytype.RedisKeyType.TOKEN_REVOKED.as_redis_key(str(self.token_obj.jti))
        if self.redis_session.get(name=redis_key):
            raise jwt.exceptions.InvalidTokenError("Token is revoked")

        return self


access_token_di = typing.Annotated[AccessTokenDI, fastapi.Depends(AccessTokenDI)]
optional_access_token_di = typing.Annotated[OptionalAccessTokenDI, fastapi.Depends(OptionalAccessTokenDI)]
refresh_token_di = typing.Annotated[RefreshTokenDI, fastapi.Depends(RefreshTokenDI)]
