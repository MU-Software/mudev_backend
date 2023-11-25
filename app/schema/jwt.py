from __future__ import annotations

import dataclasses
import datetime
import enum
import logging
import typing
import uuid

import jwt
import pydantic
import user_agents as ua

logger = logging.getLogger(__name__)


def compare_user_agent(user_agent_a_str: str, user_agent_b_str: str) -> bool:
    user_agent_a = ua.parse(user_agent_a_str)
    user_agent_b = ua.parse(user_agent_b_str)

    return all(
        (
            user_agent_a.is_mobile == user_agent_b.is_mobile,
            user_agent_a.is_tablet == user_agent_b.is_tablet,
            user_agent_a.is_pc == user_agent_b.is_pc,
            user_agent_a.os.family == user_agent_b.os.family,
            user_agent_a.browser.family == user_agent_b.browser.family,
        )
    )


class UserJWTTokenDTO(pydantic.BaseModel):
    class AccessToken(pydantic.BaseModel):
        token: str
        exp: datetime.datetime

    class RefreshToken(pydantic.BaseModel):
        exp: datetime.datetime

    access_token: AccessToken
    refresh_token: RefreshToken


class UserJWTTokenType(enum.Enum):
    @dataclasses.dataclass(frozen=True)
    class UserJWTTokenTypeSetting:
        refresh_delta: datetime.timedelta
        expiration_delta: datetime.timedelta

    refresh = UserJWTTokenTypeSetting(
        refresh_delta=datetime.timedelta(days=6),
        expiration_delta=datetime.timedelta(days=7),
    )
    access = UserJWTTokenTypeSetting(
        refresh_delta=datetime.timedelta(minutes=15),
        expiration_delta=datetime.timedelta(minutes=30),
    )


class UserJWTToken(pydantic.BaseModel):
    env: str

    # Registered Claim
    iss: str  # Token Issuer(Fixed)
    exp: pydantic.FutureDatetime  # Expiration Unix Time
    sub: UserJWTTokenType  # Token name
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

    def as_jwt(self, key: str, algorithm: str) -> str:
        return jwt.encode(payload=self.model_dump(by_alias=True), key=key, algorithm=algorithm)

    @pydantic.field_validator("sub", mode="before")
    @classmethod
    def validate_sub(cls, sub: str | UserJWTTokenType) -> UserJWTTokenType:
        return sub if isinstance(sub, UserJWTTokenType) else UserJWTTokenType[sub]

    @pydantic.model_validator(mode="after")
    def validate(self) -> typing.Self:
        if not compare_user_agent(self.request_user_agent, self.token_user_agent):
            raise jwt.exceptions.InvalidTokenError("User-Agent does not compatable")

        return self

    @pydantic.field_serializer("exp")
    def serialize_exp(self, exp: datetime.datetime) -> int:
        return int(exp.timestamp())

    @pydantic.field_serializer("sub")
    def serialize_sub(self, sub: UserJWTTokenType) -> str:
        return sub.name
