from __future__ import annotations

import datetime
import typing
import uuid

import jwt
import pydantic

import app.const.jwt as jwt_const
import app.util.mu_string as mu_string
import app.util.time_util as time_util


class UserJWTToken(pydantic.BaseModel):
    env: str

    # Registered Claim
    iss: str  # Token Issuer(Fixed)
    exp: pydantic.FutureDatetime  # Expiration Unix Time
    sub: jwt_const.UserJWTTokenType  # Token name
    jti: uuid.UUID  # JWT token ID

    # Private Claim
    user: uuid.UUID  # Audience, User, Token holder

    # Public Claim
    request_user_agent: str = pydantic.Field(exclude=True)  # User-Agent from Request
    token_user_agent: str = pydantic.Field(alias="user_agent")  # User-Agent from Token

    @classmethod
    def from_token(cls, *, token: str, key: str, algorithm: str, request_ua: str) -> UserJWTToken:
        return cls.model_validate(
            {
                **jwt.decode(jwt=token, key=key, algorithms=[algorithm]),
                "request_user_agent": request_ua,
            }
        )

    @property
    def access_token(self) -> UserJWTToken:
        if self.sub != jwt_const.UserJWTTokenType.refresh:
            raise ValueError("This token is not refresh token")

        return self.model_copy(
            update={
                "sub": jwt_const.UserJWTTokenType.access,
                "exp": time_util.get_utcnow() + jwt_const.UserJWTTokenType.access.value.expiration_delta,
            },
            deep=True,
        )

    def as_jwt(self, key: str, algorithm: str) -> str:
        return jwt.encode(payload=self.model_dump(by_alias=True), key=key, algorithm=algorithm)

    @pydantic.field_validator("sub", mode="before")
    @classmethod
    def validate_sub(cls, sub: str | jwt_const.UserJWTTokenType) -> jwt_const.UserJWTTokenType:
        return sub if isinstance(sub, jwt_const.UserJWTTokenType) else jwt_const.UserJWTTokenType[sub]

    @pydantic.model_validator(mode="after")
    def validate(self) -> typing.Self:
        if not mu_string.compare_user_agent(self.request_user_agent, self.token_user_agent):
            raise jwt.exceptions.InvalidTokenError("User-Agent does not compatable")

        return self

    @pydantic.field_serializer("exp")
    def serialize_exp(self, exp: datetime.datetime) -> int:
        return int(exp.timestamp())

    @pydantic.field_serializer("sub")
    def serialize_sub(self, sub: jwt_const.UserJWTTokenType) -> str:
        return sub.name
