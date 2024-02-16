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

    @classmethod
    def from_exception(cls, err: Exception) -> ErrorStruct:
        return cls(
            type=string_util.camel_to_snake_case(err.__class__.__name__),
            msg=str(err),
            loc=getattr(err, "loc", None),
            input=getattr(err, "input", None),
            ctx=getattr(err, "ctx", None),
            url=getattr(err, "url", None),
        )

    def __call__(self, **kwargs: tx.Unpack[ErrorStructDict]) -> ErrorStruct:
        return self.model_copy(**kwargs)

    def __repr__(self) -> str:
        result = f"{self.type}:{self.status_code}:{self.msg}"
        result += f"({self.input=})" if self.input else ""
        result += f"({self.loc=})" if self.loc else ""
        return result

    def format_msg(self, *args: object, **kwargs: object) -> ErrorStruct:
        return self(msg=self.msg.format(*args, **kwargs))

    def dump(self) -> ErrorStructDict:
        return self.model_dump(exclude_none=True, exclude_defaults=True)

    def raise_(self) -> typing.NoReturn:
        if self.should_log:
            logger.error(repr(self))
        if self.status_code == fastapi.status.HTTP_422_UNPROCESSABLE_ENTITY:
            raise fastapi.exceptions.RequestValidationError(errors=[self])
        raise fastapi.exceptions.HTTPException(status_code=self.status_code, detail=[self.dump()])

    @classmethod
    def raise_multiple(cls, errors: list[ErrorStruct]) -> typing.NoReturn:
        status_codes: set[int] = {e.status_code for e in errors}
        status_code: int = max(status_codes) if len(status_codes) > 1 else status_codes.pop()
        if status_code == fastapi.status.HTTP_422_UNPROCESSABLE_ENTITY:
            raise fastapi.exceptions.RequestValidationError(errors=errors)
        raise fastapi.exceptions.HTTPException(status_code=status_code, detail=[e.dump() for e in errors])

    def response(self) -> fastapi.responses.JSONResponse:
        content = {"detail": [self.dump()]}
        return fastapi.responses.JSONResponse(status_code=self.status_code, content=content)


class ErrorEnumMixin:
    __default_args__: dict[str, typing.Any] = {}
    __additional_args__: dict[str, typing.Any] = {}


class ErrorEnum(ErrorEnumMixin, enum.StrEnum):
    _ignore_ = ["__default_args__", "__additional_args__"]

    def __call__(self, **kwargs: tx.Unpack[ErrorStructDict]) -> ErrorStruct:
        type_name = string_util.camel_to_snake_case(f"{self.__class__.__name__}.{self.name}")
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
    DB_UNIQUE_CONSTRAINT_ERROR = "이미 등록되어 있어서 사용할 수 없어요, 다른 값을 입력해주세요."
    DB_FOREIGN_KEY_CONSTRAINT_ERROR = "{referred_table_name}에 해당 값이 존재하지 않아요, 다른 값을 입력해주세요."
    DB_NOT_NULL_CONSTRAINT_ERROR = "이 값은 필수 값이에요, 값을 입력해주세요."
    DB_RESTRICT_CONSTRAINT_ERROR = "다른 곳에서 사용하고 있어서 수정하거나 삭제할 수 없어요."
    DB_CHECK_CONSTRAINT_ERROR = "조건에 맞지 않아 등록할 수 없어요, 다른 값을 입력해주세요."
    DB_EXCLUSION_CONSTRAINT_ERROR = "다른 곳에 이미 등록되어 있어서 사용할 수 없어요, 다른 값을 입력해주세요."


class AuthNError(ErrorEnum):
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

    SIGNIN_REQUIRED = "로그인이 필요한 기능입니다, 로그인 해주세요."
    SIGNIN_FAILED = "로그인에 실패했어요, 다시 시도해주세요!"
    SIGNIN_FAILED_AS_EMAIL_NOT_VERIFIED = "이메일 인증이 완료되지 않았어요, 이메일 인증을 완료해주세요!"
    SIGNIN_USER_NOT_FOUND = "계정을 찾을 수 없어요, 이메일 또는 아이디를 확인해주세요!"
    SIGNIN_WRONG_PASSWORD = "비밀번호가 맞지 않아요, 다시 입력해주세요!"  # nosec: B105
    SIGNIN_WRONG_PASSWORD_WITH_WARNING = (
        "비밀번호가 맞지 않아요! ({allowed_count}번을 더 틀리시면 계정이 잠겨요.)"  # nosec: B105
    )

    ACCOUNT_INFO_MISMATCH = "계정 정보가 다른 곳에서 변경된 것 같아요, 새로고침 후 다시 시도해주세요."
    ACCOUNT_LOCKED = "계정이 잠겼습니다, 관리자에게 문의해주세요.\n(잠긴 이유: {reason})"
    ACCOUNT_DISABLED = "계정이 비활성화되었습니다, 관리자에게 문의해주세요.\n(비활성화 이유: {reason})"
    DEACTIVATE_FAILED_AS_ACCOUNT_LOCKED = "계정이 잠겨있어서 비활성화를 할 수 없습니다, 잠긴 계정을 해제한 후 다시 시도해주세요.\n(계정이 잠긴 이유: {reason})"
    DEACTIVATE_FAILED_AS_ACCOUNT_DEACTIVATED = (
        "계정이 이미 비활성화가 되어있어요, 이용해주셔서 감사합니다!\n계정이 비활성화된 이유: {reason})"
    )

    SELF_REVOKE_NOT_ALLOWED = "현재 로그인 중인 기기를 로그아웃하시려면, 로그아웃 기능을 사용해주세요."

    PASSWORD_CHANGE_WRONG_PASSWORD = "현재 사용 중인 비밀번호와 맞지 않아요, 다시 입력해주세요!"  # nosec: B105


class AuthZError(ErrorEnum):
    __default_args__ = {"status_code": fastapi.status.HTTP_403_FORBIDDEN, "should_log": False}

    PERMISSION_DENIED = "접근 권한이 없어요, 관리자에게 문의해주세요."

    # SNS
    BOT_USER_NOT_ALLOWED = "해당 사용자는 이 기능을 사용할 수 없습니다."
    REQUIRES_ACCOUNT_SYNC = "기능을 사용하기 위해서는 먼저 mudev.cc의 계정과 연동을 해야합니다."


class ClientError(ErrorEnum):
    __default_args__ = {"status_code": fastapi.status.HTTP_422_UNPROCESSABLE_ENTITY, "should_log": False}
    __additional_args__ = {
        "API_NOT_FOUND": ErrorStructDict(status_code=fastapi.status.HTTP_404_NOT_FOUND),
        "RESOURCE_NOT_FOUND": ErrorStructDict(status_code=fastapi.status.HTTP_404_NOT_FOUND),
        "REQUEST_TOO_FREQUENT": ErrorStructDict(status_code=fastapi.status.HTTP_429_TOO_MANY_REQUESTS),
        "REQUEST_BODY_EMPTY": ErrorStructDict(status_code=fastapi.status.HTTP_400_BAD_REQUEST),
    }

    API_NOT_FOUND = "요청하신 경로를 찾을 수 없어요, 새로고침 후 다시 시도해주세요."
    RESOURCE_NOT_FOUND = "요청하신 정보를 찾을 수 없어요."

    REQUEST_TOO_FREQUENT = "요청이 너무 빈번해요, 조금 천천히 진행해주세요."
    REQUEST_BODY_EMPTY = "입력하신 정보가 서버에 전달되지 않았어요, 새로고침 후 다시 시도해주세요."
    REQUEST_BODY_LACK = "입력하신 정보 중 누락된 부분이 있어요, 다시 입력해주세요."
    REQUEST_BODY_INVALID = "입력하신 정보가 올바르지 않아요, 다시 입력해주세요."
    REQUEST_BODY_CONTAINS_INVALID_CHAR = "입력 불가능한 문자가 포함되어 있어요, 다시 입력해주세요."
    INVALID_EMAIL = "이메일 형식이 올바르지 않아요, 이메일을 다시 입력해주세요."

    USERNAME_REQUIRED = "아이디를 입력해주세요!"
    USERNAME_TOO_SHORT = "아이디가 너무 짧아요! ({min_len}자~{max_len}자 이내로 설정해주세요)"
    USERNAME_TOO_LONG = "아이디가 너무 길어요! ({min_len}자~{max_len}자 이내로 설정해주세요)"
    USERNAME_CONTAINS_INVALID_CHAR = "아이디에 사용할 수 없는 문자가 있어요!"

    PASSWORD_REQUIRED = "비밀번호를 입력해주세요!"  # nosec: B105
    PASSWORD_TOO_SHORT = "비밀번호가 너무 짧아요! ({min_len}자~{max_len}자 이내로 설정해주세요)"  # nosec: B105
    PASSWORD_TOO_LONG = "비밀번호가 너무 길어요! (최대 {max_len}자까지 가능해요... 이렇게 긴 비밀번호는 외우기 힘드시지 않을까요?)"  # nosec: B105
    PASSWORD_CONTAINS_INVALID_CHAR = "비밀번호에 사용할 수 없는 문자가 있어요!"  # nosec: B105
    PASSWORD_NEED_MORE_CHAR_TYPE = (  # nosec: B105
        "비밀번호에는 {min_char_type_num}가지 이상의 문자 종류가 포함되어야 해요!\n"
        "(영문 대&소문자/숫자/특수문자 중 {min_char_type_num}가지 이상을 포함해주세요)"
    )


class TelegramError(ErrorEnum):
    __default_args__ = {"status_code": fastapi.status.HTTP_200_OK, "should_log": False}
    __additional_args__ = {
        "MESSAGE_NOT_GIVEN": ErrorStructDict(status_code=fastapi.status.HTTP_400_BAD_REQUEST),
    }

    USER_NOT_GIVEN = "사용자 정보가 없어요."
    USER_ALREADY_SYNCED = "이미 연동된 계정이 있어요."
    MESSAGE_NOT_GIVEN = "메시지가 비어있어요."
    HANDLER_NOT_MATCH = "무슨 말씀이신지 이해하지 못했어요, 다시 입력해주세요."
