import typing
import uuid

import argon2
import pydantic
import pydantic_core
import redis
import sqlalchemy as sa

import app.const.jwt as jwt_const
import app.const.system as system_const
import app.crud.__interface__ as crud_interface
import app.db.__type__ as db_types
import app.db.model.user as user_model
import app.redis.key_type as redis_keytype
import app.schema.user as user_schema
import app.util.time_util as time_util


class UserCRUD(crud_interface.CRUDBase[user_model.User, user_schema.UserCreate, user_schema.UserUpdate]):
    async def async_get_system_user(self, session: db_types.AsyncSessionType) -> user_model.User:
        stmt = sa.select(user_model.User).where(user_model.User.username == system_const.SYSTEM_USERNAME)
        if system_user := await self.get_using_query(session=session, query=stmt):
            return system_user
        return await self.create(session=session, obj_in=user_schema.UserCreate.for_system_user())

    def get_system_user(self, session: db_types.PossibleSessionType) -> user_model.User:
        stmt = sa.select(user_model.User).where(user_model.User.username == system_const.SYSTEM_USERNAME)
        if system_user := self.get_using_query(session=session, query=stmt):
            return system_user
        return self.create(session=session, obj_in=user_schema.UserCreate.for_system_user())

    async def signin(
        self,
        session: db_types.AsyncSessionType,
        *,
        column: db_types.ColumnableType,
        user_ident: str,
        password: str,
    ) -> user_model.User:
        stmt = sa.select(self.model).where(column == user_ident)

        if not (user := await session.scalar(stmt)):
            error: pydantic_core.InitErrorDetails = {
                "type": "value_error",
                "loc": ("username",),
                "msg": "계정을 찾을 수 없어요, 이메일 또는 아이디를 확인해주세요!",
                "input": user_ident,
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
            argon2.PasswordHasher().verify(user.password, password)
            user.mark_as_signin_succeed()
            return await crud_interface.commit_and_return(session=session, db_obj=user)
        except argon2.exceptions.VerifyMismatchError:
            user.mark_as_signin_failed()
            await session.commit()
            raise ValueError(
                user.signin_disabled_reason_message
                or user_model.SignInDisabledReason.WRONG_PASSWORD.value.format(**user.dict)
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
        user_schema.UserSignInHistoryCreate,
        user_schema.UserSignInHistoryUpdate,
    ]
):
    def delete(self, *args: tuple, **kwargs: dict) -> typing.NoReturn:  # type: ignore[override]
        err_msg = "UserSignInHistoryCRUD.delete is not implemented. Use UserSignInHistoryCRUD.revoke instead."
        raise NotImplementedError(err_msg)

    async def get_using_token_obj(
        self, session: db_types.AsyncSessionType, *, token_obj: user_schema.UserJWTToken
    ) -> user_model.UserSignInHistory:
        if not (db_obj := await self.get(session=session, uuid=token_obj.jti)):
            raise ValueError("로그인 기록을 찾을 수 없습니다!")
        return db_obj

    async def signin(
        self, session: db_types.AsyncSessionType, *, obj_in: user_schema.UserSignInHistoryCreate
    ) -> user_schema.RefreshToken:
        db_obj = await self.create(session=session, obj_in=obj_in)
        return user_schema.RefreshToken.from_orm(signin_history=db_obj, config_obj=obj_in.config_obj)

    async def refresh(
        self,
        session: db_types.AsyncSessionType,
        *,
        token_obj: user_schema.RefreshToken,
    ) -> user_schema.RefreshToken:
        if token_obj.should_refresh:
            db_obj = await self.get_using_token_obj(session=session, token_obj=token_obj)
            new_expires_at = time_util.get_utcnow() + jwt_const.UserJWTTokenType.refresh.value.expiration_delta
            token_obj.exp = db_obj.expires_at = new_expires_at
            await session.commit()
        return token_obj

    async def revoke(
        self,
        session: db_types.AsyncSessionType,
        redis_session: redis.Redis,
        *,
        token_obj: user_schema.UserJWTToken,
    ) -> None:
        db_obj = await self.get_using_token_obj(session=session, token_obj=token_obj)
        db_obj.deleted_at = db_obj.expires_at = sa.func.now()
        await session.commit()

        redis_key = redis_keytype.RedisKeyType.TOKEN_REVOKED.as_redis_key(str(uuid))
        redis_session.set(redis_key, "1", ex=jwt_const.UserJWTTokenType.refresh.value.expiration_delta)


userCRUD = UserCRUD(model=user_model.User)
userSignInHistoryCRUD = UserSignInHistoryCRUD(model=user_model.UserSignInHistory)
