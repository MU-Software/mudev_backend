from __future__ import annotations

import enum
import logging
import typing

import fastapi
import pydantic
import typing_extensions as tx

import app.util.mu_string as string_util

logger = logging.getLogger(__name__)


class ErrorStructDict(typing.TypedDict):
    type: typing.NotRequired[str]
    msg: typing.NotRequired[str]
    loc: typing.NotRequired[list[str]]
    input: typing.NotRequired[typing.Any]
    ctx: typing.NotRequired[dict[str, typing.Any]]
    url: typing.NotRequired[str]

    status_code: typing.NotRequired[int]
    should_log: typing.NotRequired[bool]


class ErrorStruct(pydantic.BaseModel):
    type: str
    msg: str
    loc: list[str] | None = None
    input: typing.Any | None = None
    ctx: dict[str, typing.Any] | None = None
    url: pydantic.HttpUrl | None = None

    status_code: int = pydantic.Field(default=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, exclude=True)
    should_log: bool = pydantic.Field(default=True, exclude=True)

    def __call__(self, **kwargs: tx.Unpack[ErrorStructDict]) -> ErrorStruct:
        return self.model_copy(**kwargs)

    def __repr__(self) -> str:
        result = f"{self.type}:{self.status_code}:{self.msg}"
        result += f"({self.input=})" if self.input else ""
        result += f"({self.loc=})" if self.loc else ""
        return result

    def dump(self) -> ErrorStructDict:
        return self.model_dump(exclude_none=True, exclude_defaults=True)

    def raise_(self) -> typing.NoReturn:
        if self.should_log:
            logger.error(repr(self))
        if self.status_code == fastapi.status.HTTP_422_UNPROCESSABLE_ENTITY:
            raise fastapi.exceptions.RequestValidationError(errors=[self])
        raise fastapi.exceptions.HTTPException(status_code=self.status_code, detail=self.dump())

    @classmethod
    def raise_multiple(cls, errors: list[ErrorStruct]) -> typing.NoReturn:
        status_codes: set[int] = {e.status_code for e in errors}
        status_code: int = max(status_codes) if len(status_codes) > 1 else status_codes.pop()
        if status_code == fastapi.status.HTTP_422_UNPROCESSABLE_ENTITY:
            raise fastapi.exceptions.RequestValidationError(errors=errors)
        raise fastapi.exceptions.HTTPException(status_code=status_code, detail=[e.dump() for e in errors])

    def response(self) -> fastapi.responses.JSONResponse:
        content = {"detail": self.dump()}
        return fastapi.responses.JSONResponse(status_code=self.status_code, content=content)


class ErrorEnumMixin:
    __default_args__: dict[str, typing.Any] = {}
    __additional_args__: dict[str, typing.Any] = {}


class ErrorEnum(ErrorEnumMixin, enum.StrEnum):
    _ignore_ = ["__default_args__", "__additional_args__"]

    def __call__(self, **kwargs: tx.Unpack[ErrorStructDict]) -> ErrorStruct:
        type_name = string_util.camel_to_snake_case(self.__class__.__name__)
        return ErrorStruct(
            **{
                "type": type_name,
                "msg": self.value,
                **self.__default_args__,
                **self.__additional_args__.get(self.name, {}),
                **kwargs,
            }
        )


class ServerError(ErrorEnum):
    __default_args__ = {"status_code": fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, "should_log": True}

    UNKNOWN_SERVER_ERROR = "알 수 없는 문제가 발생했습니다, 5분 후에 다시 시도해주세요."
    CRITICAL_SERVER_ERROR = "서버에 치명적인 문제가 발생했습니다, 관리자에게 문의해주시면 감사하겠습니다."


class DBServerError(ErrorEnum):
    __default_args__ = {"status_code": fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR, "should_log": True}

    DB_CONNECTION_ERROR = "알 수 없는 문제가 발생했습니다, 5분 후에 다시 시도해주세요."
    DB_UNKNOWN_ERROR = "알 수 없는 문제가 발생했습니다, 5분 후에 다시 시도해주세요."
    DB_CRITICAL_ERROR = "서버에 치명적인 문제가 발생했습니다, 관리자에게 문의해주시면 감사하겠습니다."
    DB_INTEGRITY_CONSTRAINT_ERROR = "기존에 저장된 데이터가 완전하거나 정확하지 않아요, 관리자에게 문의해주세요."


class DBValueError(ErrorEnum):
    __default_args__ = {"status_code": fastapi.status.HTTP_422_UNPROCESSABLE_ENTITY, "should_log": True}

    DB_DATA_ERROR = "올바르지 않은 값이에요, 다른 값을 입력해주세요."
    DB_UNIQUE_CONSTRAINT_ERROR = "입력하신 값이 이미 존재해요, 다른 값을 입력해주세요."
    DB_FOREIGN_KEY_CONSTRAINT_ERROR = "{referred_table_name}에 해당 값이 존재하지 않아요, 다른 값을 입력해주세요."
    DB_NOT_NULL_CONSTRAINT_ERROR = "이 값은 필수 값이에요, 값을 입력해주세요."
    DB_RESTRICT_CONSTRAINT_ERROR = "다른 곳에서 참조하고 있어서 수정하거나 삭제할 수 없어요."
    DB_CHECK_CONSTRAINT_ERROR = "조건에 맞지 않는 값이에요, 다른 값을 입력해주세요."
    DB_EXCLUSION_CONSTRAINT_ERROR = "다른 곳에 등록되어 있어서 등록할 수 없어요, 다른 값을 입력해주세요."


class AuthError(ErrorEnum):
    __default_args__ = {"status_code": fastapi.status.HTTP_401_UNAUTHORIZED, "should_log": False}
    __additional_args__ = {
        "INVALID_ACCESS_TOKEN": ErrorStructDict(loc=["header", "authorization"]),
        "INVALID_REFRESH_TOKEN": ErrorStructDict(loc=["cookie", "refresh_token"]),
        "SIGNIN_FAILED": ErrorStructDict(loc=["body", "username"]),
        "SIGNIN_USER_NOT_FOUND": ErrorStructDict(loc=["body", "username"]),
    }

    INVALID_ACCESS_TOKEN = "유효하지 않은 인증 정보에요, 인증 정보를 갱신해주세요."  # nosec: B105
    INVALID_REFRESH_TOKEN = "로그인 정보가 만료되었어요, 다시 로그인해주세요."  # nosec: B105

    AUTH_USER_NOT_FOUND = "로그인 정보를 찾을 수 없어요, 다시 로그인해주세요."
    AUTH_HISTORY_NOT_FOUND = "로그인 기록을 찾을 수 없어요, 다시 로그인해주세요."

    SIGNIN_FAILED = "로그인에 실패했어요, 다시 시도해주세요!"
    SIGNIN_USER_NOT_FOUND = "계정을 찾을 수 없어요, 이메일 또는 아이디를 확인해주세요!"

    SELF_REVOKE_NOT_ALLOWED = "현재 로그인 중인 기기를 로그아웃하시려면, 로그아웃 기능을 사용해주세요."
