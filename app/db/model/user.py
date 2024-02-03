from __future__ import annotations

import enum
import typing

import argon2
import sqlalchemy as sa
import sqlalchemy.orm as sa_orm

import app.config.fastapi as fastapi_config
import app.const.jwt as jwt_const
import app.db.__mixin__ as db_mixin
import app.db.__type__ as db_types
import app.util.sqlalchemy as sqlalchemy_util
import app.util.time_util as time_util

config_obj = fastapi_config.get_fastapi_setting()
ALLOWED_SIGNIN_FAILURES = config_obj.route.account.allowed_signin_failures
SIGNIN_POSSIBLE_AFTER_MAIL_VERIFICATION = config_obj.route.account.signin_possible_after_mail_verification


class SignInDisabledReason(enum.StrEnum):
    EMAIL_NOT_VERIFIED = "이메일 인증이 완료되지 않았습니다. 이메일을 확인해주세요."
    WRONG_PASSWORD = (
        "비밀번호가 일치하지 않습니다.\n" "({leftover_signin_failed_attempt}번 더 틀리면 계정이 잠겨요.)"
    )  # nosec B105
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
    password: sa_orm.Mapped[db_types.Str]
    password_updated_at: sa_orm.Mapped[db_types.DateTime] = sa_orm.mapped_column(default=sa.func.now())

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

    @property
    def dict(self) -> typing.Dict[str, typing.Any]:
        return sqlalchemy_util.orm2dict(self) | {
            "leftover_signin_failed_attempt": ALLOWED_SIGNIN_FAILURES - self.signin_fail_count
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
            return reason.format(**self.dict)

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


class UserSignInStatus(enum.StrEnum):
    ACTIVE = enum.auto()
    REFRESH_REQUIRED = enum.auto()
    REVOKED = enum.auto()
    EXPIRED = enum.auto()


class UserSignInHistory(db_mixin.DefaultModelMixin):
    user_uuid: sa_orm.Mapped[db_types.UserFK]

    ip: sa_orm.Mapped[db_types.Str]
    user_agent: sa_orm.Mapped[db_types.Str]
    client_token: sa_orm.Mapped[db_types.Str_Nullable]

    expires_at: sa_orm.Mapped[db_types.DateTime]
    next_uuid: sa_orm.Mapped[db_types.NullableForeignKeyTypeGenerator("usersigninhistory.uuid")]  # noqa: F821

    @property
    def status(self) -> UserSignInStatus:
        if self.next_uuid:
            # TODO: REFRESH_REQUIRED는 권한 갱신 등 현재 토큰은 만료됐지만 다음 토큰으로 갱신해야 할 시 발생할 수 있습니다.
            return UserSignInStatus.REFRESH_REQUIRED

        if self.expires_at < time_util.get_utcnow():
            if self.deleted_at == self.expires_at:
                return UserSignInStatus.REVOKED
            return UserSignInStatus.EXPIRED

        claimed_at = self.expires_at - jwt_const.UserJWTTokenType.refresh.value.expiration_delta
        if claimed_at + jwt_const.UserJWTTokenType.refresh.value.refresh_delta < time_util.get_utcnow():
            # 곧 만료될 토큰이므로 갱신이 필요합니다.
            return UserSignInStatus.REFRESH_REQUIRED

        return UserSignInStatus.ACTIVE
