from __future__ import annotations

import contextlib
import email.utils
import enum
import functools
import re
import string
import typing
import unicodedata

import pydantic
import user_agents as ua

USERNAME_MIN_LEN = 4
USERNAME_MAX_LEN = 48
PW_MIN_LEN = 8
PW_MAX_LEN = 1024
PW_MIN_CHAR_TYPE_NUM = 2

# ---------- Check and Normalize strings ----------
char_printable: str = string.ascii_letters + string.digits + string.punctuation
char_urlsafe: str = string.ascii_letters + string.digits + "-_"
char_useridsafe: str = string.ascii_letters + string.digits


def normalize(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def is_printable(s: str) -> bool:
    return all(c in char_printable for c in s)


def is_urlsafe(s: str) -> bool:
    return all(c in char_urlsafe for c in s)


def is_email(s: str) -> bool:
    with contextlib.suppress(BaseException):
        if parsed_email := email.utils.parseaddr(normalize(s))[1]:
            splited_mail_address: list[str] = parsed_email.split("@")
            splited_domain: list[str] = splited_mail_address[1].split(".")
            return (
                len(splited_mail_address) == 2
                and all(splited_mail_address)
                and len(splited_domain) >= 2
                and all(splited_domain)
            )
    return False


# ---------- Case modifier ----------
def camel_to_snake_case(camel: str) -> str:
    camel = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", camel)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", camel).lower()


def snake_to_camel_case(snake: str) -> str:
    return "".join(word.title() for word in snake.split("_"))


def snake_to_train_case(snake: str) -> str:
    """Convert a snake_case string to Train-Case.

    Args:
        snake: The string to convert.

    Returns:
        The Train-Case string.
    """
    return snake.title().replace("_", "-")


class CharType(enum.StrEnum):
    LOWER = enum.auto()
    UPPER = enum.auto()
    DIGIT = enum.auto()
    PUNCT = enum.auto()

    @classmethod
    def get_char_type(cls, s: str) -> CharType | None:
        c_type: dict[CharType, str] = {
            cls.LOWER: string.ascii_lowercase,
            cls.UPPER: string.ascii_uppercase,
            cls.DIGIT: string.digits,
            cls.PUNCT: string.punctuation,
        }
        for key, value in c_type.items():
            if normalize(s) in value:
                return key
        return None

    @classmethod
    def get_str_char_types(cls, target_str: str) -> set[CharType | None]:
        return {cls.get_char_type(target_char) for target_char in target_str}


class UserNameValidator(enum.StrEnum):
    SAFE = enum.auto()

    # User ID validation failure code
    EMPTY = enum.auto()
    TOO_SHORT = enum.auto()
    TOO_LONG = enum.auto()
    FORBIDDEN_CHAR = enum.auto()

    @classmethod
    def is_valid(cls, s: str, min_len: int, max_len: int) -> UserNameValidator:
        if not s:
            return cls.EMPTY
        if min_len > len(s):
            return cls.TOO_SHORT
        if len(s) > max_len:
            return cls.TOO_LONG

        if not is_urlsafe(s):
            return cls.FORBIDDEN_CHAR

        return cls.SAFE

    @classmethod
    def validate_username(cls, value: str, min_len: int, max_len: int) -> str:
        match cls.is_valid(value, min_len=min_len, max_len=max_len):
            case cls.SAFE:
                return value
            case cls.EMPTY:
                raise ValueError("ID를 입력해주세요!")
            case cls.TOO_SHORT:
                raise ValueError(f"ID가 너무 짧아요! (최소 {min_len}자 이상으로 설정해주세요)")
            case cls.TOO_LONG:
                raise ValueError(f"ID가 너무 길어요! (최대 {max_len}까지 가능해요)")
            case cls.FORBIDDEN_CHAR:
                raise ValueError("ID에 사용할 수 없는 문자가 있어요!")
            case _:
                raise ValueError("알 수 없는 오류가 발생했어요! 관리자에게 문의해주세요!")


UsernameField = typing.Annotated[
    str,
    pydantic.functional_validators.BeforeValidator(
        functools.partial(
            UserNameValidator.validate_username,
            min_len=USERNAME_MIN_LEN,
            max_len=USERNAME_MAX_LEN,
        ),
    ),
]


class PasswordValidator(enum.StrEnum):
    SAFE = enum.auto()

    # Password validation failure code
    EMPTY = enum.auto()
    TOO_SHORT = enum.auto()
    TOO_LONG = enum.auto()
    NEED_MORE_CHAR_TYPE = enum.auto()
    FORBIDDEN_CHAR = enum.auto()

    # Password change failure code
    WRONG_PASSWORD = enum.auto()
    PW_REUSED_ON_ID_EMAIL_NICK = enum.auto()
    UNKNOWN_ERROR = enum.auto()

    @classmethod
    def is_valid(cls, s: str, min_char_type_num: int, min_len: int, max_len: int) -> PasswordValidator:
        if not s:
            return cls.EMPTY
        if len(s) < min_len:
            return cls.TOO_SHORT
        if max_len < len(s):
            return cls.TOO_LONG

        s_char_type: set[CharType | None] = CharType.get_str_char_types(s)
        if len(s_char_type) < min_char_type_num:
            return cls.NEED_MORE_CHAR_TYPE

        if not all(s_char_type):
            return cls.FORBIDDEN_CHAR

        return cls.SAFE

    @classmethod
    def validate_password(cls, value: str, min_len: int, max_len: int, min_char_type_num: int) -> str:
        match cls.is_valid(value, min_len=min_len, max_len=max_len, min_char_type_num=min_char_type_num):
            case cls.SAFE:
                return value
            case cls.EMPTY:
                raise ValueError("비밀번호를 입력해주세요!")
            case cls.TOO_SHORT:
                raise ValueError(f"비밀번호가 너무 짧아요! (최소 {min_len}자 이상으로 설정해주세요)")
            case cls.TOO_LONG:
                raise ValueError("비밀번호가 너무 길어요!\n" f"(최대 {max_len}자까지 가능해요...이렇게 긴 비밀번호는 외우기 힘드시지 않을까요?)")
            case cls.NEED_MORE_CHAR_TYPE:
                raise ValueError(
                    f"비밀번호에는 {min_char_type_num}가지 이상의 문자 종류가 포함되어야 해요!\n"
                    f"(영문 대문자, 영문 소문자, 숫자, 특수문자 중 {min_char_type_num}가지 이상을 포함해주세요)"
                )
            case cls.FORBIDDEN_CHAR:
                raise ValueError("비밀번호에 사용할 수 없는 문자가 있어요!")
            case _:
                raise ValueError("알 수 없는 오류가 발생했어요! 관리자에게 문의해주세요!")


PasswordField = typing.Annotated[
    str,
    pydantic.functional_validators.BeforeValidator(
        functools.partial(
            PasswordValidator.validate_password,
            min_len=PW_MIN_LEN,
            max_len=PW_MAX_LEN,
            min_char_type_num=PW_MIN_CHAR_TYPE_NUM,
        ),
    ),
]


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
