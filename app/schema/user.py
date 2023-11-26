from __future__ import annotations

import datetime
import typing
import uuid

import argon2
import fastapi
import jwt
import pydantic
import pydantic_core
import sqlalchemy as sa

import app.config.fastapi as fastapi_config
import app.const.jwt as jwt_const
import app.db.model.user as user_model
import app.util.fastapi.cookie as cookie_util
import app.util.mu_json as mu_json
import app.util.mu_string as mu_string
import app.util.pydantic.normalizer as normalizer
import app.util.pydantic.with_model as with_model
import app.util.time_util as time_util


class UserDTO(pydantic.BaseModel):
    uuid: uuid.UUID
    username: mu_string.UsernameField
    nickname: str
    email: pydantic.EmailStr
    email_verified_at: pydantic.PastDatetime | None = None

    created_at: datetime.datetime
    modified_at: datetime.datetime
    deleted_at: datetime.datetime | None = None
    locked_at: datetime.datetime | None = None
    last_signin_at: datetime.datetime | None = None

    private: bool = False
    description: str | None = None
    profile_image: str | None = None
    website: str | None = None
    location: str | None = None

    class Config:
        from_attributes = True


class UserSignInHistoryDTO(pydantic.BaseModel):
    ip: pydantic.IPvAnyAddress
    user_agent: str

    created_at: datetime.datetime
    modified_at: datetime.datetime
    deleted_at: datetime.datetime | None = None
    expires_at: datetime.datetime

    class Config:
        from_attributes = True


class UserCreate(normalizer.NormalizerModelMixin):  # A.k.a. Sign Up
    username: mu_string.UsernameField
    nickname: str
    email: pydantic.EmailStr

    password: mu_string.PasswordField
    password_confirm: str = pydantic.Field(exclude=True)

    private: bool = False
    description: str | None = None
    profile_image: str | None = None
    website: str | None = None
    location: str | None = None
    birth: datetime.date | None = None

    @pydantic.model_validator(mode="after")
    def validate_model(self) -> typing.Self:
        if self.password != self.password_confirm:
            raise ValueError("확인을 위해 다시 입력해주신 비밀번호가 일치하지 않아요, 다시 한 번 확인해주세요!")

        password_containable_fields = (self.email, self.username, self.nickname)
        if any(self.password.lower() in z.lower() for z in password_containable_fields):
            raise ValueError("비밀번호가 ID, 이메일, 또는 닉네임과 너무 비슷해요! 다른 비밀번호를 입력해주세요!")

        return self

    @pydantic.field_serializer("password", when_used="always")
    def serialize_password(self, v: str) -> str:
        """DB에 비밀번호의 해시를 저장하도록 합니다."""
        return argon2.PasswordHasher().hash(v)


class UserUpdate(normalizer.NormalizerModelMixin, with_model.WithSAModelMixin[user_model.User]):
    username: mu_string.UsernameField
    nickname: str

    private: bool = False
    description: str | None = None
    profile_image: str | None = None
    website: str | None = None
    location: str | None = None
    birth: datetime.date | None = None


class UserPasswordUpdate(normalizer.NormalizerModelMixin):
    original_password: mu_string.PasswordField = pydantic.Field(exclude=True)
    new_password: mu_string.PasswordField = pydantic.Field(exclude=True)
    new_password_confirm: str = pydantic.Field(exclude=True)

    @pydantic.model_validator(mode="after")
    def validate_model(self) -> typing.Self:
        if self.new_password != self.new_password_confirm:
            raise ValueError("확인을 위해 다시 입력해주신 비밀번호가 일치하지 않아요, 다시 한 번 확인해주세요!")

        return self


class UserPasswordUpdateForModel(UserPasswordUpdate, with_model.WithSAModelMixin[user_model.User]):
    username: mu_string.UsernameField = pydantic.Field(exclude=True)
    nickname: str = pydantic.Field(exclude=True)
    email: pydantic.EmailStr = pydantic.Field(exclude=True)

    locked_at: datetime.datetime | None = pydantic.Field(exclude=True)
    deleted_at: datetime.datetime | None = pydantic.Field(exclude=True)

    password: str  # DB record of current password, hashed

    @pydantic.field_validator("original_password", mode="after")
    @classmethod
    def validate_original_password(cls, value: str, info: pydantic_core.core_schema.ValidationInfo) -> str:
        try:
            argon2.PasswordHasher().verify(info.data["password"], value)
        except argon2.exceptions.VerifyMismatchError:
            raise ValueError("기존 비밀번호와 일치하지 않아요!")

        return value

    @pydantic.model_validator(mode="after")
    def validate_model(self) -> typing.Self:
        super().validate_model()

        password_containable_fields = (self.username, self.nickname, self.email)
        if any(self.password.lower() in z.lower() for z in password_containable_fields):
            raise ValueError("비밀번호가 ID, 이메일, 또는 닉네임과 너무 비슷해요! 다른 비밀번호를 입력해주세요!")

        return self


class UserSignIn(normalizer.NormalizerModelMixin):
    user_ident: mu_string.UsernameField | pydantic.EmailStr | str
    password: str

    @property
    def signin_type(self) -> tuple[sa.ColumnElement, str]:
        if self.user_ident.startswith("@"):
            return user_model.User.username, self.user_ident[1:]
        elif "@" in self.user_ident and mu_string.is_email(self.user_ident):
            return user_model.User.email, self.user_ident
        return user_model.User.username, self.user_ident


class UserSignInHistoryCreate(pydantic.BaseModel):
    user_uuid: uuid.UUID
    ip: pydantic.IPvAnyAddress
    user_agent: str

    @pydantic.computed_field  # type: ignore[misc]
    @property
    def expires_at(self) -> datetime.datetime:
        return time_util.get_utcnow() + jwt_const.UserJWTTokenType.refresh.value.expiration_delta


class UserSignInHistoryUpdate(pydantic.BaseModel):
    ...


class UserJWTToken(pydantic.BaseModel):
    # Registered Claim
    iss: str  # Token Issuer(Fixed)
    exp: pydantic.FutureDatetime  # Expiration Unix Time
    sub: jwt_const.UserJWTTokenType  # Token name
    jti: uuid.UUID  # JWT token ID

    # Private Claim
    user: uuid.UUID  # Audience, User, Token holder

    # Public Claim
    user_agent: str  # User-Agent from Token
    request_user_agent: str = pydantic.Field(exclude=True)  # User-Agent from Request

    # For encryption and decryption
    key: str = pydantic.Field(exclude=True)

    JWT_FIELD: typing.ClassVar[set[str]] = {"iss", "exp", "sub", "jti", "user", "user_agent"}

    @classmethod
    def from_token(cls, *, token: str, key: str, request_ua: str) -> UserJWTToken:
        return cls.model_validate(
            {
                **jwt.decode(jwt=token, key=key, algorithms=["HS256"]),
                "key": key,
                "request_user_agent": request_ua,
            }
        )

    @classmethod
    def _from_orm(
        cls,
        *,
        sub: jwt_const.UserJWTTokenType,
        signin_history: user_model.UserSignInHistory,
        config_obj: fastapi_config.FastAPISetting,
        key: str,
    ) -> UserJWTToken:
        return cls(
            sub=sub,
            key=key,
            exp=signin_history.expires_at,
            jti=signin_history.uuid,
            user=signin_history.user_uuid,
            user_agent=signin_history.user_agent,
            request_user_agent=signin_history.user_agent,
            iss=config_obj.server_name,
        )

    @property
    def dict(self) -> dict[str, typing.Any]:
        return dict(self)

    @property
    def jwt(self) -> str:
        payload = mu_json.dict_to_jsonable_dict({k: v for k, v in self.dict.items() if k in self.JWT_FIELD})
        return jwt.encode(payload=payload, key=self.key)

    def set_cookie(self, config_obj: fastapi_config.FastAPISetting, response: fastapi.Response) -> None:
        if not self.sub.value.cookie_key:
            raise ValueError("This token is not cookie token")

        cookie_util.Cookie(
            **self.sub.value.cookie_key.to_cookie_config(),
            **config_obj.to_cookie_config(),
            value=self.jwt,
            expires=self.exp,
        ).set_cookie(response=response)

    @pydantic.field_validator("sub", mode="before")
    @classmethod
    def validate_sub(cls, sub: str | jwt_const.UserJWTTokenType) -> jwt_const.UserJWTTokenType:
        return sub if isinstance(sub, jwt_const.UserJWTTokenType) else jwt_const.UserJWTTokenType[sub]

    @pydantic.model_validator(mode="after")
    def validate_model(self) -> typing.Self:
        if not mu_string.compare_user_agent(self.request_user_agent, self.user_agent):
            raise jwt.exceptions.InvalidTokenError("User-Agent does not compatable")

        return self

    @pydantic.field_serializer("exp")
    def serialize_exp(self, exp: datetime.datetime) -> int:
        return int(exp.timestamp())

    @pydantic.field_serializer("sub")
    def serialize_sub(self, sub: jwt_const.UserJWTTokenType) -> str:
        return sub.name


class RefreshToken(UserJWTToken):
    sub: typing.Literal[jwt_const.UserJWTTokenType.refresh]

    @classmethod
    def from_orm(
        cls,
        *,
        signin_history: user_model.UserSignInHistory,
        config_obj: fastapi_config.FastAPISetting,
    ) -> RefreshToken:
        return cls._from_orm(
            sub=jwt_const.UserJWTTokenType.refresh,
            signin_history=signin_history,
            config_obj=config_obj,
            key=config_obj.secret_key.get_secret_value(),
        )

    @pydantic.model_serializer(mode="plain", when_used="always")
    def serialize_model(self) -> dict[str, str | datetime.datetime]:
        return {"exp": self.exp}

    def to_access_token(self, csrf_token: str) -> AccessToken:
        return AccessToken.model_validate(
            self.dict
            | {
                "key": self.key + csrf_token,
                "sub": jwt_const.UserJWTTokenType.access,
                "exp": time_util.get_utcnow() + jwt_const.UserJWTTokenType.access.value.expiration_delta,
                "user_agent": self.user_agent,  # We need to set explicitly as this is aliased
            }
        )


class AccessToken(UserJWTToken):
    sub: typing.Literal[jwt_const.UserJWTTokenType.access]

    @classmethod
    def from_orm(
        cls,
        *,
        signin_history: user_model.UserSignInHistory,
        config_obj: fastapi_config.FastAPISetting,
        csrf_token: str,
    ) -> RefreshToken:
        return cls._from_orm(
            sub=jwt_const.UserJWTTokenType.access,
            signin_history=signin_history,
            config_obj=config_obj,
            key=config_obj.secret_key.get_secret_value() + csrf_token,
        )

    @pydantic.model_serializer(mode="plain", when_used="always")
    def serialize_model(self) -> dict[str, str | datetime.datetime]:
        return {"token": self.jwt, "exp": self.exp}


class UserJWTDTO(pydantic.BaseModel):
    access_token: AccessToken
    refresh_token: RefreshToken


class UserSignInDTO(pydantic.BaseModel):
    user: UserDTO
    token: UserJWTDTO
