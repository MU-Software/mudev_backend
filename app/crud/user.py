import typing
import uuid

import argon2
import pydantic
import pydantic_core
import redis
import sqlalchemy as sa

import app.const.jwt as jwt_const
import app.crud.__interface__ as crud_interface
import app.db.__type__ as db_types
import app.db.model.user as user_model
import app.redis.key_type as redis_keytype
import app.schema.jwt as jwt_schema
import app.schema.user as user_schema
import app.util.time_util as time_util


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
        user_schema.UserSignInHistoryCreate,
        user_schema.UserSignInHistoryUpdate,
    ]
):
    def update(self, *args: tuple, **kwargs: dict) -> typing.NoReturn:  # type: ignore[override]
        raise NotImplementedError("UserSignInHistoryCRUD.update is not implemented.")

    def delete(self, *args: tuple, **kwargs: dict) -> typing.NoReturn:  # type: ignore[override]
        err_msg = "UserSignInHistoryCRUD.delete is not implemented. Use UserSignInHistoryCRUD.revoke instead."
        raise NotImplementedError(err_msg)

    async def revoke(
        self,
        session: db_types.AsyncSessionType,
        redis_session: redis.Redis,
        *,
        uuid: str | uuid.UUID,
        user_uuid: str | uuid.UUID,
    ) -> None:
        db_obj: user_model.UserSignInHistory = await self.get(session=session, uuid=uuid)
        if not (db_obj and db_obj.is_valid(user_uuid)):
            raise ValueError("로그인 기록을 찾을 수 없습니다!")

        db_obj.deleted_at = db_obj.expires_at = sa.func.now()
        await session.commit()

        redis_key = redis_keytype.RedisKeyType.TOKEN_REVOKED.as_redis_key(str(uuid))
        redis_session.set(redis_key, "1", ex=jwt_const.UserJWTTokenType.refresh.value.expiration_delta)

    async def claim_token(
        self,
        session: db_types.AsyncSessionType,
        redis_session: redis.Redis,
        *,
        db_obj: user_model.UserSignInHistory,
        user_uuid: str | uuid.UUID,
        issuer: str,
        request_user_agent: str,
    ) -> jwt_schema.UserJWTToken:
        refresh_token_type = jwt_const.UserJWTTokenType.refresh

        redis_key = redis_keytype.RedisKeyType.TOKEN_REVOKED.as_redis_key(str(db_obj.uuid))
        if redis_session.get(redis_key):
            if not db_obj.next_uuid:
                raise ValueError("로그인 기록이 만료되었습니다!")
            db_obj = await self.get(session=session, uuid=db_obj.next_uuid)

        validation_result = db_obj.is_valid(user_uuid, request_user_agent)
        match (validation_result):
            case user_model.UserSignInHistoryValidationCase.EXPIRED:
                if not db_obj.next_uuid:
                    raise ValueError("로그인 기록이 만료되었습니다!")
                db_obj = await self.get(session=session, uuid=db_obj.next_uuid)
            case user_model.UserSignInHistoryValidationCase.NOT_FOR_THIS_USER:
                raise ValueError("로그인 기록을 찾을 수 없습니다!")

        if db_obj.expires_at + refresh_token_type.value.refresh_delta < time_util.get_utcnow():
            db_obj.expires_at = time_util.get_utcnow() + refresh_token_type.value.expiration_delta

        db_obj.user_agent = request_user_agent
        await session.commit()

        return jwt_schema.UserJWTToken(
            iss=issuer,
            exp=db_obj.expires_at,
            sub=refresh_token_type,
            jti=db_obj.uuid,
            user=db_obj.user_uuid,
            request_user_agent=db_obj.user_agent,
            token_user_agent=db_obj.user_agent,
        )


userCRUD = UserCRUD(model=user_model.User)
userSignInHistoryCRUD = UserSignInHistoryCRUD(model=user_model.UserSignInHistory)
