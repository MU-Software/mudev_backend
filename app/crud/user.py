import typing
import uuid

import argon2
import sqlalchemy as sa

import app.config.fastapi as fastapi_config
import app.crud.__interface__ as crud_interface
import app.db.__type__ as db_types
import app.db.model.user as user_model
import app.schema.user as user_schema

config_obj = fastapi_config.get_fastapi_setting()
ALLOWED_SIGNIN_FAILURES = config_obj.route.account.allowed_signin_failures
SIGNIN_POSSIBLE_AFTER_MAIL_VERIFICATION = config_obj.route.account.signin_possible_after_mail_verification


class UserCRUD(crud_interface.CRUDBase[user_model.User, user_schema.UserCreate, user_schema.UserUpdate]):
    async def signin(self, session: db_types.AsyncSessionType, *, obj_in: user_schema.UserSignIn) -> user_model.User:
        user_ident_column, user_ident_value = obj_in.signin_type
        stmt = sa.select(self.model).where(user_ident_column == user_ident_value)

        if not (user := await session.scalar(stmt)):
            raise ValueError("계정을 찾을 수 없어요, 이메일 또는 아이디를 확인해주세요!")
        elif signin_disabled_reason_msg := user.signin_disabled_reason_message:
            raise ValueError(signin_disabled_reason_msg)

        try:
            argon2.PasswordHasher().verify(user.password, obj_in.password)
            user.mark_as_signin_succeed()
            await session.commit()
            await session.refresh(user)  # TODO: Remove this line
            return user
        except argon2.exceptions.VerifyMismatchError:
            user.mark_as_signin_failed()
            await session.commit()
            await session.refresh(user)  # TODO: Remove this line
            raise ValueError(
                user.signin_disabled_reason_message
                or user_model.SignInDisabledReason.WRONG_PASSWORD.value.format(**user.to_dict())
            )

    async def update_password(
        self, session: db_types.AsyncSessionType, *, uuid: str | uuid.UUID, obj_in: user_schema.UserPasswordUpdate
    ) -> typing.Awaitable[user_model.User]:
        if not (user := await self.get(session=session, uuid=uuid)):
            raise ValueError("계정을 찾을 수 없습니다!")

        user.set_password(
            user_schema.UserPasswordUpdateForModel.model_validate_with_orm(
                orm_obj=user,
                data=obj_in.model_dump(),
            ).new_password,
        )
        await session.commit()
        return user


userCRUD = UserCRUD(model=user_model.User)
