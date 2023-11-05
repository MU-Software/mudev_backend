from __future__ import annotations

import contextlib
import datetime
import enum

import sqlalchemy as sa
import sqlalchemy.ext.asyncio as sa_async
import sqlalchemy.orm as sa_orm
from passlib.hash import argon2

import app.config.fastapi as fastapi_config
import app.db.__mixin__ as db_mixin
import app.db.__type__ as db_types
import app.util.mu_string as mu_string
import app.util.time_util as time_util

config_obj = fastapi_config.get_fastapi_setting()
ALLOWED_SIGNIN_FAILURES = config_obj.route.account.allowed_signin_failures
SIGNIN_POSSIBLE_AFTER_MAIL_VERIFICATION = config_obj.route.account.signin_possible_after_mail_verification


class SignInFailedReason(enum.StrEnum):
    # NOT_FOUND
    ACCOUNT_NOT_FOUND = "계정을 찾을 수 없습니다."

    # NOT_VERIFIED
    ACCOUNT_NOT_VERIFIED = "계정이 인증되지 않았습니다. 이메일을 확인해주세요."
    EMAIL_NOT_VERIFIED = "이메일 인증이 완료되지 않았습니다. 이메일을 확인해주세요."

    # WRONG_PASSWORD
    WRONG_PASSWORD = "비밀번호가 일치하지 않습니다. {}번 더 틀리면 계정이 잠겨요."  # nosec B105

    # LOCKED
    TOO_MUCH_LOGIN_FAIL = "로그인 실패 횟수가 너무 많습니다. 비밀번호를 변경해주세요."

    # DEACTIVATED
    SELF_DEACTIVATED = "계정이 비활성화 되었습니다. 관리자에게 문의해주세요."
    ADMIN_DEACTIVATED = "관리자에 의해 계정이 비활성화 되었습니다. 관리자에게 문의해주세요."
    ADMIN_DELETED = "관리자에 의해 계정이 삭제되었습니다. 관리자에게 문의해주세요."

    # UNKNOWN
    UNKNOWN = "알 수 없는 오류가 발생했습니다. 잠시 후 다시 시도해주시고, 문제가 지속되면 관리자에게 문의해주세요."


class SignInFailedException(Exception):
    def __init__(self, reason: SignInFailedReason = SignInFailedReason.UNKNOWN, *args, **kwargs):
        self.reason = reason
        kwargs.setdefault("message", reason.value)
        super().__init__(*args, **kwargs)


class User(db_mixin.DefaultModelMixin):
    username: sa_orm.Mapped[db_types.Str_Unique]
    nickname: sa_orm.Mapped[db_types.Str_Unique]
    password: sa_orm.Mapped[str]
    password_changed_at: sa_orm.Mapped[datetime.datetime] = sa_orm.mapped_column(default=sa.func.now())

    # No, We won't support multiple email account
    email: sa_orm.Mapped[db_types.Str_Unique]
    email_verified: sa_orm.Mapped[db_types.Bool_DFalse]
    email_secret: sa_orm.Mapped[str | None]

    last_signin_at: sa_orm.Mapped[datetime.datetime]
    signin_fail_count: sa_orm.Mapped[int] = sa_orm.mapped_column(default=0)
    signin_failed_at: sa_orm.Mapped[datetime.datetime | None]

    locked_at: sa_orm.Mapped[datetime.datetime | None]
    locked_reason_code: sa_orm.Mapped[str | None]
    locked_reason_description: sa_orm.Mapped[str | None]

    deactivated_at: sa_orm.Mapped[datetime.datetime | None]
    deactivated_reason_code: sa_orm.Mapped[str | None]
    deactivated_reason_description: sa_orm.Mapped[str | None]
    deactivated_by_id: sa_orm.Mapped[db_types.UserFK_Nullable]
    deactivated_by = sa_orm.relationship("User", primaryjoin="User.deactivated_by_id == User.uuid")

    private: sa_orm.Mapped[db_types.Bool_DFalse]
    description: sa_orm.Mapped[str | None]
    profile_image: sa_orm.Mapped[db_types.Str_Nullable]  # This will point to user profile image url
    website: sa_orm.Mapped[str | None]
    location: sa_orm.Mapped[str | None]
    birth: sa_orm.Mapped[datetime.date | None]

    def check_password(self, password: str) -> bool:
        if not self.password:
            return False

        # Try verification with password they entered without trimming.
        # If it fails, silently try it with trimming.
        with contextlib.suppress(Exception):
            normalized_password = mu_string.normalize(password).strip()
            return argon2.verify(password, self.password) or argon2.verify(normalized_password, self.password)
        return False

    async def change_password(
        self, session: sa_async.AsyncSession, old_password: str, new_password: str, force_change: bool = False
    ) -> mu_string.PasswordValidator:
        # We'll trim space on user input
        normalized_old_password = mu_string.normalize(old_password).strip()
        normalized_new_password = mu_string.normalize(new_password).strip()

        pw_str_check = mu_string.PasswordValidator.is_valid(normalized_new_password)
        if pw_str_check != mu_string.PasswordValidator.SAFE:
            return pw_str_check

        if not (force_change or self.check_password(normalized_old_password)):
            return mu_string.PasswordValidator.WRONG_PASSWORD

        if any(normalized_new_password.lower() in z.lower() for z in (self.username, self.email, self.nickname)):
            return mu_string.PasswordValidator.PW_REUSED_ON_ID_EMAIL_NICK

        self.password = argon2.hash(normalized_new_password)
        self.password_changed_at = time_util.get_utcnow()
        await session.commit()
        return mu_string.PasswordValidator.SAFE

    async def change_username(self, session: sa_async.AsyncSession, new_id: str) -> mu_string.UserNameValidator:
        normalized_new_id = mu_string.normalize(new_id).strip()
        username_str_check = mu_string.UserNameValidator.is_valid(normalized_new_id)

        if username_str_check == mu_string.UserNameValidator.SAFE:
            self.id = new_id
            await session.commit()

        return username_str_check

    @classmethod
    async def try_signin(cls, session: sa_async.AsyncSession, user_ident: str, password: str) -> User:
        def get_login_type(user_ident: str) -> tuple[sa.sql.ColumnElement, str]:
            normalized_user_ident = mu_string.normalize(user_ident).strip().lower()

            if user_ident.startswith("@"):
                return User.username, normalized_user_ident[1:]
            elif "@" in user_ident and mu_string.is_email(user_ident):
                return User.email, normalized_user_ident
            return User.username, normalized_user_ident

        login_type, normalized_user_ident = get_login_type(user_ident)
        user_query = sa.select(User).where(login_type == normalized_user_ident).with_for_update(of=User)
        self: User | None = await session.scalar(user_query)
        if not self:
            raise SignInFailedException(SignInFailedReason.ACCOUNT_NOT_FOUND)

        if SIGNIN_POSSIBLE_AFTER_MAIL_VERIFICATION and not self.email_verified:
            raise SignInFailedException(reason=SignInFailedReason.EMAIL_NOT_VERIFIED)
        elif self.locked_at:
            raise SignInFailedException(
                reason=SignInFailedReason(self.locked_reason_code),
                message=self.locked_reason_description,
            )
        elif self.deactivated_at:
            raise SignInFailedException(
                reason=SignInFailedReason(self.deactivated_reason_code),
                message=self.deactivated_reason_description,
            )
        elif not self.check_password(password):
            self.signin_fail_count += 1
            self.signin_failed_at = sa.func.now()

            reason_code: SignInFailedReason = SignInFailedReason.WRONG_PASSWORD
            reason_message: str = SignInFailedReason.WRONG_PASSWORD.value.format(
                ALLOWED_SIGNIN_FAILURES - self.signin_fail_count
            )

            if self.signin_fail_count >= ALLOWED_SIGNIN_FAILURES:
                self.locked_at = sa.func.now()
                self.locked_reason_code = SignInFailedReason.TOO_MUCH_LOGIN_FAIL.name
                self.locked_reason_description = SignInFailedReason.TOO_MUCH_LOGIN_FAIL.value

                reason_code = SignInFailedReason.TOO_MUCH_LOGIN_FAIL
                reason_message = SignInFailedReason.TOO_MUCH_LOGIN_FAIL.value

            await session.commit()
            raise SignInFailedException(reason=reason_code, message=reason_message)

        # If password is correct and account is not locked, process signin.
        self.last_signin_at = sa.func.now()
        self.signin_fail_count = 0
        self.signin_failed_at = None

        await session.commit()
        return self


class UserSignInHistory(db_mixin.DefaultModelMixin):
    user_uuid: sa_orm.Mapped[db_types.UserFK]
    ip: sa_orm.Mapped[db_types.Str]
    user_agent: sa_orm.Mapped[db_types.Str]
