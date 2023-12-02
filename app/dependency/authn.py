from __future__ import annotations

import functools
import typing

import fastapi
import jwt
import pydantic

import app.const.cookie as cookie_const
import app.const.header as header_const
import app.crud.user as user_crud
import app.db.model.user as user_model
import app.dependency.common as common_dep
import app.dependency.header as header_dep
import app.redis.key_type as redis_keytype
import app.schema.user as user_schema

TokenSchema = typing.TypeVar("TokenSchema", bound=user_schema.UserJWTToken)


class BaseTokenDI(typing.Generic[TokenSchema], pydantic.BaseModel):
    _db_session: common_dep.dbDI
    _redis_session: common_dep.redisDI

    config_obj: common_dep.settingDI
    user_ip: header_dep.user_ip
    user_agent: header_dep.user_agent
    csrf_token: header_dep.csrf_token

    base_class: typing.ClassVar[typing.Type[TokenSchema]] = user_schema.UserJWTToken  # type: ignore[misc]
    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    @property
    def key(self) -> str:
        return self.config_obj.secret_key.get_secret_value()

    @property
    def token_str(self) -> str:
        raise NotImplementedError

    @functools.cached_property
    def signin_history(self) -> user_model.UserSignInHistory:
        return user_crud.userSignInHistoryCRUD.get(self._db_session, self.token_obj.jti)

    @functools.cached_property
    def user(self) -> user_model.User:
        return user_crud.userCRUD.get(self._db_session, self.token_obj.user)

    @functools.cached_property
    def token_obj(self) -> TokenSchema:
        return self.base_class.from_token(
            token=self.token_str,
            key=self.key,
            request_user_agent=self.user_agent,
            config_obj=self.config_obj,
        )

    @pydantic.model_validator(mode="after")
    def validate_model(self) -> typing.Self:
        # Check token revocation
        redis_key: str = redis_keytype.RedisKeyType.TOKEN_REVOKED.as_redis_key(str(self.token_obj.jti))
        if self._redis_session.get(name=redis_key):
            raise jwt.exceptions.InvalidTokenError("Token is revoked")

        return self


class RefreshTokenDI(BaseTokenDI[user_schema.RefreshToken], pydantic.BaseModel):
    refresh_token: typing.Annotated[str, cookie_const.CookieKey.REFRESH_TOKEN.as_cookie()]
    base_class = user_schema.RefreshToken

    @property
    def token_str(self) -> str:
        return self.refresh_token


class AccessTokenDI(BaseTokenDI[user_schema.AccessToken], pydantic.BaseModel):
    authorization: typing.Annotated[str, header_const.HeaderKey.ACCESS_TOKEN.as_header()]
    base_class = user_schema.AccessToken

    @property
    def key(self) -> str:
        return super().key + self.csrf_token

    @property
    def token_str(self) -> str:
        return self.authorization.replace("Bearer ", "")


class OptionalAccessTokenDI(AccessTokenDI, pydantic.BaseModel):
    csrf_token: header_dep.csrf_token | None = None
    authorization: typing.Annotated[str | None, header_const.HeaderKey.ACCESS_TOKEN.as_header()] = None

    @property
    def token_str(self) -> str | None:
        return self.authorization.replace("Bearer ", "") if self.authorization else None

    @functools.cached_property
    def token_obj(self) -> user_schema.AccessToken | None:
        return super().token_obj if self.authorization else None

    @functools.cached_property
    def signin_history(self) -> user_model.UserSignInHistory | None:
        return super().signin_history if self.authorization else None

    @functools.cached_property
    def user(self) -> user_model.User | None:
        return super().user if self.authorization else None


access_token_di = typing.Annotated[AccessTokenDI, fastapi.Depends(AccessTokenDI)]
optional_access_token_di = typing.Annotated[OptionalAccessTokenDI, fastapi.Depends(OptionalAccessTokenDI)]
refresh_token_di = typing.Annotated[RefreshTokenDI, fastapi.Depends(RefreshTokenDI)]
