import typing
import uuid

import argon2
import pydantic
import pydantic_core
import redis
import sqlalchemy as sa

import app.config.fastapi as fastapi_config
import app.crud.__interface__ as crud_interface
import app.db.__type__ as db_types
import app.db.model.user as user_model
import app.schema.signin_history as signin_history_schema
import app.schema.user as user_schema

config_obj = fastapi_config.get_fastapi_setting()
ALLOWED_SIGNIN_FAILURES = config_obj.route.account.allowed_signin_failures
SIGNIN_POSSIBLE_AFTER_MAIL_VERIFICATION = config_obj.route.account.signin_possible_after_mail_verification


class UserCRUD(crud_interface.CRUDBase[user_model.User, user_schema.UserCreate, user_schema.UserUpdate]):
    async def signin(self, session: db_types.AsyncSessionType, *, obj_in: user_schema.UserSignIn) -> user_model.User:
        user_ident_column, user_ident_value = obj_in.signin_type
        stmt = sa.select(self.model).where(user_ident_column == user_ident_value)

        if not (user := await session.scalar(stmt)):
            error: pydantic_core.InitErrorDetails = {
                "type": "value_error",
                "loc": ("user_ident",),
                "msg": "계정을 찾을 수 없어요, 이메일 또는 아이디를 확인해주세요!",
                "input": user_ident_value,
                "ctx": {"error": ValueError("계정을 찾을 수 없어요, 이메일 또는 아이디를 확인해주세요!")},
                "url": "https://errors.pydantic.dev/2/v/value_error",
            }
            raise pydantic.ValidationError.from_exception_data(
                title="1 validation error for UserSignIn",
                line_errors=[error],
            )
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
    ) -> user_model.User:
        user: user_model.User = await self.get(session=session, uuid=uuid)
        if not user:
            raise ValueError("계정을 찾을 수 없습니다!")

        user.set_password(
            user_schema.UserPasswordUpdateForModel.model_validate_with_orm(
                orm_obj=user,
                data=obj_in.model_dump(),
            ).new_password,
        )
        return await crud_interface.commit_and_return(session=session, db_obj=user)


class UserSignInHistoryCRUD(
    crud_interface.CRUDBase[
        user_model.UserSignInHistory,
        signin_history_schema.UserSignInHistoryCreate,
        signin_history_schema.UserSignInHistoryUpdate,
    ]
):
    def delete(self, session: db_types.PossibleSessionType, *, uuid: str | uuid.UUID) -> typing.NoReturn:
        raise NotImplementedError(
            "UserSignInHistoryCRUD.delete is not implemented. " "Use UserSignInHistoryCRUD.revoke instead."
        )

    async def revoke(
        self,
        session: db_types.AsyncSessionType,
        redis_session: redis.Redis,
        *,
        uuid: str | uuid.UUID,
        user_uuid: str | uuid.UUID,
    ) -> None:
        # TODO: Implement this
        pass

    async def claim_token(self, session: db_types.AsyncSessionType, *, uuid: str | uuid.UUID) -> None:
        # TODO: Implement this
        pass

    async def signin(
        self,
        session: db_types.AsyncSessionType,
        *,
        obj_in: signin_history_schema.UserSignInHistoryCreate,
        csrf_token: str,
    ) -> typing.Awaitable[user_model.UserSignInHistory]:
        signin_history = await self.create(session=session, obj_in=obj_in)
        await session.commit()
        return signin_history


userCRUD = UserCRUD(model=user_model.User)
userSignInHistoryCRUD = UserSignInHistoryCRUD(model=user_model.UserSignInHistory)
