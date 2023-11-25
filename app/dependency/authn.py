from __future__ import annotations

import dataclasses
import functools
import typing

import fastapi
import jwt

import app.const.cookie as cookie_const
import app.crud.user as user_crud
import app.db.model.user as user_model
import app.dependency.common as common_dep
import app.dependency.header as header_dep
import app.redis.key_type as redis_keytype
import app.schema.jwt as jwt_schema
import app.util.fastapi.cookie as cookie_util


@dataclasses.dataclass
class AccessTokenDI:
    setting: common_dep.setting_dep
    db_session: common_dep.dbDI
    redis_session: common_dep.redisDI
    user_agent: header_dep.user_agent
    csrf_token: header_dep.csrf_token
    authorization: typing.Annotated[str, fastapi.Header("Authorization")]

    token_obj: jwt_schema.UserJWTToken = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        # Parse token and validate
        self.token_obj = jwt_schema.UserJWTToken.from_token(
            token=self.authorization.replace("Bearer ", ""),
            key=self.setting.secret_key + self.csrf_token,
            algorithm=self.setting.security.jwt_algorithm,
            request_ua=self.user_agent,
        )

        # Check token revocation
        redis_key: str = redis_keytype.RedisKeyType.TOKEN_REVOKED.as_redis_key(str(self.token_obj.jti))
        if self.redis_session.get(name=redis_key):
            raise jwt.exceptions.InvalidTokenError("Token is revoked")

    @functools.cached_property
    def user(self) -> user_model.User:
        return user_crud.userCRUD.get(self.db_session, self.token_obj.user)


@dataclasses.dataclass
class OptionalAccessTokenDI(AccessTokenDI):
    authorization: typing.Annotated[str | None, fastapi.Header("Authorization")] = None
    token_obj: jwt_schema.UserJWTToken | None = None

    def __post_init__(self) -> None:
        if self.authorization:
            super().__post_init__()

    @functools.cached_property
    def user(self) -> user_model.User | None:
        return None if not self.authorization else super().user


@dataclasses.dataclass
class RefreshTokenDI:
    setting: common_dep.setting_dep
    db_session: common_dep.dbDI
    redis_session: common_dep.redisDI
    user_agent: header_dep.user_agent
    csrf_token: header_dep.csrf_token
    refresh_token: typing.Annotated[str, fastapi.Cookie]

    token_obj: jwt_schema.UserJWTToken = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        # Parse token and validate
        self.token_obj = jwt_schema.UserJWTToken.from_token(
            token=self.refresh_token,
            key=self.setting.secret_key,
            algorithm=self.setting.security.jwt_algorithm,
            request_ua=self.user_agent,
        )

        # Check token revocation
        redis_key = redis_keytype.RedisKeyType.TOKEN_REVOKED.as_redis_key(str(self.token_obj.jti))
        if self.redis_session.get(name=redis_key):
            raise jwt.exceptions.InvalidTokenError("Token is revoked")

    @functools.cached_property
    def signin_history(self) -> user_model.UserSignInHistory:
        return user_crud.userSignInHistoryCRUD.get(self.db_session, self.token_obj.jti)

    @functools.cached_property
    def user(self) -> user_model.User:
        return user_crud.userCRUD.get(self.db_session, self.token_obj.user)

    @property
    def access_token(self) -> str:
        access_token_obj = self.token_obj.model_copy(update={"sub": jwt_schema.UserJWTTokenType.access}, deep=True)
        return access_token_obj.as_jwt(
            key=self.setting.secret_key + self.csrf_token,
            algorithm=self.setting.security.jwt_algorithm,
        )

    @property
    def cookie(self) -> cookie_util.Cookie:
        return cookie_util.Cookie(
            key=cookie_const.CookieKey.REFRESH_TOKEN.value,
            value=self.refresh_token,
            expires=self.token_obj.exp,
            **self.setting.to_cookie_config(),
        )


access_token_di = typing.Annotated[AccessTokenDI, fastapi.Depends(AccessTokenDI)]
optional_access_token_di = typing.Annotated[OptionalAccessTokenDI, fastapi.Depends(OptionalAccessTokenDI)]
refresh_token_di = typing.Annotated[RefreshTokenDI, fastapi.Depends(RefreshTokenDI)]
