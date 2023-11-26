from __future__ import annotations

import datetime
import enum
import typing
import uuid

import argon2
import sqlalchemy as sa
import sqlalchemy.orm as sa_orm

import app.config.fastapi as fastapi_config
import app.db.__mixin__ as db_mixin
import app.db.__type__ as db_types
import app.util.mu_string as mu_string
import app.util.sqlalchemy as sa_util
import app.util.time_util as time_util

config_obj = fastapi_config.get_fastapi_setting()
ALLOWED_SIGNIN_FAILURES = config_obj.route.account.allowed_signin_failures
SIGNIN_POSSIBLE_AFTER_MAIL_VERIFICATION = config_obj.route.account.signin_possible_after_mail_verification


class SignInDisabledReason(enum.StrEnum):
    EMAIL_NOT_VERIFIED = "이메일 인증이 완료되지 않았습니다. 이메일을 확인해주세요."
    WRONG_PASSWORD = "비밀번호가 일치하지 않습니다.\n" "({leftover_signin_failed_attempt}번 더 틀리면 계정이 잠겨요.)"  # nosec B105
    UNKNOWN = "알 수 없는 오류가 발생했습니다. 잠시 후 다시 시도해주시고, 문제가 지속되면 관리자에게 문의해주세요."

    # LOCKED
    TOO_MUCH_LOGIN_FAIL = "로그인 실패 횟수가 너무 많습니다, 비밀번호를 변경해주세요."
    LOCKED = "관리자에 의해 계정이 비활성화 되었습니다. 관리자에게 문의해주세요.\n(사유 : {locked_reason})"

    # DELETED
    SELF_DELETED = "{deleted_at:%Y년 %m월 %d일 %H시 %M분}에 탈퇴한 계정입니다."
    ADMIN_DELETED = "관리자에 의해 계정이 삭제되었습니다. 관리자에게 문의해주세요."


class User(db_mixin.DefaultModelMixin):
    username: sa_orm.Mapped[db_types.Str_Unique]
    nickname: sa_orm.Mapped[db_types.Str_Unique]
    password: sa_orm.Mapped[str]
    password_updated_at: sa_orm.Mapped[datetime.datetime] = sa_orm.mapped_column(default=sa.func.now())

    # No, We won't support multiple email account
    email: sa_orm.Mapped[db_types.Str_Unique]
    email_verified_at: sa_orm.Mapped[db_types.DateTime_Nullable]
    email_secret: sa_orm.Mapped[db_types.Str_Nullable]

    last_signin_at: sa_orm.Mapped[db_types.DateTime_Nullable]
    signin_fail_count: sa_orm.Mapped[int] = sa_orm.mapped_column(default=0)
    signin_failed_at: sa_orm.Mapped[db_types.DateTime_Nullable]

    locked_at: sa_orm.Mapped[db_types.DateTime_Nullable]
    locked_by_uuid: sa_orm.Mapped[db_types.UserFK_Nullable]
    locked_reason: sa_orm.Mapped[db_types.Str_Nullable]

    deleted_by_uuid: sa_orm.Mapped[db_types.UserFK_Nullable]

    private: sa_orm.Mapped[db_types.Bool_DFalse]
    description: sa_orm.Mapped[db_types.Str_Nullable]
    profile_image: sa_orm.Mapped[db_types.Str_Nullable]  # This will point to user profile image url
    website: sa_orm.Mapped[db_types.Str_Nullable]
    location: sa_orm.Mapped[db_types.Str_Nullable]
    birth: sa_orm.Mapped[db_types.Date_Nullable]

    def to_dict(self) -> dict[str, typing.Any]:
        return {
            **sa_util.orm2dict(self),
            "leftover_signin_failed_attempt": ALLOWED_SIGNIN_FAILURES - self.signin_fail_count,
        }

    @property
    def signin_disabled_reason(self) -> SignInDisabledReason | None:
        if SIGNIN_POSSIBLE_AFTER_MAIL_VERIFICATION and not self.email_verified_at:
            return SignInDisabledReason.EMAIL_NOT_VERIFIED

        elif self.deleted_at:
            if self.deleted_by_uuid == self.uuid:
                return SignInDisabledReason.SELF_DELETED
            return SignInDisabledReason.ADMIN_DELETED

        elif self.locked_at:
            return SignInDisabledReason.LOCKED

        return None

    @property
    def signin_disabled_reason_message(self) -> str | None:
        if reason := self.signin_disabled_reason:
            return reason.format(self.to_dict())

        return None

    def set_password(self, password: str) -> None:
        if self.locked_reason == SignInDisabledReason.TOO_MUCH_LOGIN_FAIL.value:
            # 잠긴 사유가 로그인 실패 횟수 초과인 경우에만 계정 잠금을 해제합니다.
            self.locked_at = None
            self.locked_reason = None

        self.signin_fail_count = 0
        self.signin_failed_at = None
        self.password = argon2.PasswordHasher().hash(password)
        self.password_updated_at = sa.func.now()

    def mark_as_signin_succeed(self) -> None:
        self.signin_fail_count = 0
        self.signin_failed_at = None
        self.last_signin_at = sa.func.now()

    def mark_as_signin_failed(self) -> None:
        self.signin_fail_count += 1
        self.signin_failed_at = sa.func.now()

        if self.signin_fail_count >= ALLOWED_SIGNIN_FAILURES:
            self.locked_at = sa.func.now()
            self.locked_reason = SignInDisabledReason.TOO_MUCH_LOGIN_FAIL.value


class UserSignInHistoryValidationCase(enum.StrEnum):
    VALID = enum.auto()
    EXPIRED = enum.auto()
    NOT_FOR_THIS_USER = enum.auto()


class UserSignInHistory(db_mixin.DefaultModelMixin):
    user_uuid: sa_orm.Mapped[db_types.UserFK]

    ip: sa_orm.Mapped[db_types.Str]
    user_agent: sa_orm.Mapped[db_types.Str]

    expires_at: sa_orm.Mapped[datetime.datetime]
    next_uuid: sa_orm.Mapped[db_types.ForeignKeyTypeGenerator("usersigninhistory.uuid")]  # noqa: F821

    def is_valid(self, user_uuid: str | uuid.UUID, user_agent: str | None = None) -> UserSignInHistoryValidationCase:
        # TODO: is_valid should not be a method of UserSignInHistory. (This should not be here!)
        if self.user_uuid != user_uuid:
            return UserSignInHistoryValidationCase.NOT_FOR_THIS_USER

        if user_agent and not mu_string.compare_user_agent(self.user_agent, user_agent):
            return UserSignInHistoryValidationCase.NOT_FOR_THIS_USER

        if self.deleted_at or self.expires_at < time_util.get_utcnow():
            return UserSignInHistoryValidationCase.EXPIRED

        return UserSignInHistoryValidationCase.VALID
