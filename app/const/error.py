from __future__ import annotations

import dataclasses
import enum
import typing

import pydantic
import pydantic_core


class CommonErrorMsg:
    UNKNOWN_SERVER_ERROR = "알 수 없는 문제가 발생했습니다, 5분 후에 다시 시도해주세요."
    CRITICAL_SERVER_ERROR = "서버에 치명적인 문제가 발생했습니다, 관리자에게 문의해주시면 감사하겠습니다."
    DB_INTEGRITY_CONSTRAINT_ERROR = "기존에 저장된 데이터가 완전하거나 정확하지 않아요, 관리자에게 문의해주세요."

    DB_DATA_ERROR = "올바르지 않은 값이에요, 다른 값을 입력해주세요."
    DB_UNIQUE_CONSTRAINT_ERROR = "입력하신 값이 이미 존재해요, 다른 값을 입력해주세요."
    DB_FOREIGN_KEY_CONSTRAINT_ERROR = "{referred_table_name}에 해당 값이 존재하지 않아요, 다른 값을 입력해주세요."
    DB_NOT_NULL_CONSTRAINT_ERROR = "이 값은 필수 값이에요, 값을 입력해주세요."
    DB_RESTRICT_CONSTRAINT_ERROR = "다른 곳에서 참조하고 있어서 수정하거나 삭제할 수 없어요."
    DB_CHECK_CONSTRAINT_ERROR = "조건에 맞지 않는 값이에요, 다른 값을 입력해주세요."
    DB_EXCLUSION_CONSTRAINT_ERROR = "다른 곳에 등록되어 있어서 등록할 수 없어요, 다른 값을 입력해주세요."

    INVALID_ACCESS_TOKEN = "유효하지 않은 인증 정보에요, 인증 정보를 갱신해주세요."  # nosec: B105
    INVALID_REFRESH_TOKEN = "로그인 정보가 만료되었어요, 다시 로그인해주세요."  # nosec: B105


class ErrorStruct(pydantic.BaseModel):
    type: str = "server_error"
    msg: str = CommonErrorMsg.UNKNOWN_SERVER_ERROR
    loc: list[str] = pydantic.Field(default_factory=list)
    input: typing.Any | None = None
    ctx: dict[str, typing.Any] | None = None
    url: str | None = None

    # Internal error message
    log_msg: str | None = pydantic.Field(default=None, exclude=True)

    @classmethod
    def value_error(cls, msg: str, field_name: str | None = None, input: typing.Any | None = None) -> ErrorStruct:
        loc = [field_name] if field_name else []
        url = "https://errors.pydantic.dev/2/v/value_error"
        return cls(type="value_error", loc=loc, msg=msg, input=input, ctx={"error": ValueError(msg)}, url=url)

    @pydantic.model_validator(mode="after")
    def validate(self) -> typing.Self:
        self.log_msg = self.log_msg or self.msg
        return self

    def update(self, **kwargs: typing.Any) -> AuthError:
        self.value = dataclasses.replace(self, **kwargs)
        return self


def errorstruct_to_validationerror(errors: list[ErrorStruct]) -> pydantic_core.ValidationError:
    return pydantic_core.ValidationError.from_exception_data(
        title=f"{len(errors)} validation error{'s' if len(errors) > 1 else ''} for {errors[0].type}",
        line_errors=[e.model_dump() for e in errors],
    )


class ServerError(enum.Enum):
    DB_CONNECTION_ERROR = ErrorStruct(log_msg="DB_CONNECTION_ERROR")
    DB_UNKNOWN_ERROR = ErrorStruct(log_msg="DB_UNKNOWN_ERROR")
    DB_CRITICAL_ERROR = ErrorStruct(msg=CommonErrorMsg.CRITICAL_SERVER_ERROR, log_msg="DB_CRITICAL_ERROR")
    DB_DATA_ERROR = ErrorStruct(msg=CommonErrorMsg.DB_DATA_ERROR, type="value_error")
    DB_INTEGRITY_CONSTRAINT_ERROR = ErrorStruct(msg=CommonErrorMsg.DB_INTEGRITY_CONSTRAINT_ERROR, type="value_error")


class AuthError(enum.Enum):
    INVALID_ACCESS_TOKEN = ErrorStruct(
        msg=CommonErrorMsg.INVALID_ACCESS_TOKEN,
        loc=("header", "authorization"),
        log_msg="INVALID_ACCESS_TOKEN",
        type="auth_error",
    )
    INVALID_REFRESH_TOKEN = ErrorStruct(
        msg=CommonErrorMsg.INVALID_REFRESH_TOKEN,
        loc=("cookie", "refresh_token"),
        log_msg="INVALID_REFRESH_TOKEN",
        type="auth_error",
    )
