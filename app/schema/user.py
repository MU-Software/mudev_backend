import datetime
import typing
import uuid

import argon2
import pydantic
import pydantic_core
import sqlalchemy as sa

import app.const.jwt as jwt_const
import app.db.model.user as user_model
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

    class Config:
        from_attributes = True


class UserJWTTokenDTO(pydantic.BaseModel):
    class AccessToken(pydantic.BaseModel):
        token: str
        exp: datetime.datetime

    class RefreshToken(pydantic.BaseModel):
        exp: datetime.datetime

    access_token: AccessToken
    refresh_token: RefreshToken


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
    def validate(self) -> typing.Self:
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
    def validate(self) -> typing.Self:
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
    def validate(self) -> typing.Self:
        super().validate()

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
