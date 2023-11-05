from __future__ import annotations

import contextlib
import email.utils
import enum
import string
import unicodedata

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

    WRONG_PASSWORD = enum.auto()
    UNKNOWN_ERROR = enum.auto()

    @classmethod
    def is_valid(cls, s: str) -> UserNameValidator:
        if 4 > len(s):
            return cls.TOO_SHORT
        if len(s) > 48:
            return cls.TOO_LONG

        if not is_urlsafe(s):
            return cls.FORBIDDEN_CHAR

        return cls.SAFE


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
    def is_valid(cls, s: str, min_char_type_num: int = 2, min_len: int = 8, max_len: int = 1024) -> PasswordValidator:
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
