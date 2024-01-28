import contextlib
import uuid

import argon2
import redis
import sqlalchemy as sa

import app.const.error as error_const
import app.const.jwt as jwt_const
import app.const.sns as sns_const
import app.const.system as system_const
import app.crud.__interface__ as crud_interface
import app.db.__type__ as db_types
import app.db.model.user as user_model
import app.redis.key_type as redis_keytype
import app.schema.user as user_schema
import app.util.mu_string as string_util
import app.util.time_util as time_util


class UserCRUD(crud_interface.CRUDBase[user_model.User, user_schema.UserCreate, user_schema.UserUpdate]):
    async def async_get_system_user(self, session: db_types.As) -> user_model.User:
        stmt = sa.select(user_model.User).where(user_model.User.username == system_const.SYSTEM_USERNAME)
        if system_user := await self.get_using_query(session=session, query=stmt):
            return system_user
        return await self.create(session=session, obj_in=user_schema.UserCreate.for_system_user())

    def get_system_user(self, session: db_types.Ps) -> user_model.User:
        stmt = sa.select(user_model.User).where(user_model.User.username == system_const.SYSTEM_USERNAME)
        if system_user := self.get_using_query(session=session, query=stmt):
            return system_user
        return self.create(session=session, obj_in=user_schema.UserCreate.for_system_user())

    async def signin(self, session: db_types.As, user_ident: str, password: str) -> user_model.User:
        if user_ident.startswith("@"):
            column, user_ident = user_model.User.username, user_ident[1:]
        elif "@" in user_ident and string_util.is_email(user_ident):
            column, user_ident = user_model.User.email, user_ident
        else:
            column, user_ident = user_model.User.username, user_ident

        stmt = sa.select(self.model).where(column == user_ident)

        if not (user := await session.scalar(stmt)):
            error_const.AuthError.SIGNIN_USER_NOT_FOUND().raise_()
        elif error_msg := user.signin_disabled_reason_message:
            error_const.AuthError.SIGNIN_FAILED(msg=error_msg, input=user_ident).raise_()

        with contextlib.suppress(argon2.exceptions.VerifyMismatchError):
            argon2.PasswordHasher().verify(user.password, password)
            user.mark_as_signin_succeed()
            return await crud_interface.commit_and_return(session=session, db_obj=user)

        user.mark_as_signin_failed()
        await session.commit()

        default_err_msg = user_model.SignInDisabledReason.WRONG_PASSWORD.value.format(**user.dict)
        error_msg = user.signin_disabled_reason_message or default_err_msg
        error_const.AuthError.SIGNIN_FAILED(msg=error_msg, input=user_ident).raise_()

    async def update_password(
        self, session: db_types.As, uuid: uuid.UUID, obj_in: user_schema.UserPasswordUpdate
    ) -> user_model.User:
        if not (user := await self.get(session=session, uuid=uuid)):
            error_const.AuthError.AUTH_USER_NOT_FOUND().raise_()

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
        crud_interface.EmptySchema,
    ]
):
    async def delete(  # type: ignore[override]
        self, session: db_types.As, redis_session: redis.Redis, token: user_schema.UserJWTToken
    ) -> None:
        if not (db_obj := await self.get_using_token_obj(session=session, token=token)):
            error_const.AuthError.AUTH_HISTORY_NOT_FOUND().raise_()
        db_obj.deleted_at = db_obj.expires_at = sa.func.now()
        await session.commit()

        redis_key = redis_keytype.RedisKeyType.TOKEN_REVOKED.as_redis_key(str(token.user))
        redis_session.set(redis_key, "1", ex=jwt_const.UserJWTTokenType.refresh.value.expiration_delta)

    async def get_using_token_obj(
        self, session: db_types.As, token: user_schema.UserJWTToken
    ) -> user_model.UserSignInHistory:
        if not (db_obj := await self.get(session=session, uuid=token.jti)):
            error_const.AuthError.AUTH_HISTORY_NOT_FOUND().raise_()
        return db_obj

    async def signin(
        self, session: db_types.As, obj_in: user_schema.UserSignInHistoryCreate
    ) -> user_schema.RefreshToken:
        db_obj = await self.create(session=session, obj_in=obj_in)
        await session.refresh(db_obj)
        return user_schema.RefreshToken.from_orm(signin_history=db_obj, config_obj=obj_in.config_obj)

    async def refresh(self, session: db_types.As, token: user_schema.RefreshToken) -> user_schema.RefreshToken:
        if token.should_refresh:
            if not (db_obj := await self.get_using_token_obj(session=session, token=token)):
                error_const.AuthError.AUTH_HISTORY_NOT_FOUND().raise_()
            new_expires_at = time_util.get_utcnow() + jwt_const.UserJWTTokenType.refresh.value.expiration_delta
            token.exp = db_obj.expires_at = new_expires_at
            await session.commit()
        return token


class SNSAuthInfoCRUD(
    crud_interface.CRUDBase[user_model.UserSignInHistory, user_schema.SNSAuthInfoCreate, crud_interface.EmptySchema]
):
    async def sns_user_to_user(
        self,
        session: db_types.As,
        sns_type: sns_const.SNSAuthInfoUserAgentEnum,
        user_id: int | None,
    ) -> uuid.UUID | None:
        if not user_id:
            return None

        stmt = sa.select(self.model).where(
            self.model.user_agent == sns_type.value,
            self.model.client_token == str(user_id),
            # 삭제되지 않았거나 만료되지 않은 토큰만 사용
            sa.or_(self.model.deleted_at.is_(None), self.model.expires_at > sa.func.now()),
        )
        return auth.user_uuid if (auth := await self.get_using_query(session=session, query=stmt)) else None

    def get_user_sns_tokens(
        self,
        session: db_types.Ss,
        user_uuid: uuid.UUID,
        sns_type: sns_const.SNSAuthInfoUserAgentEnum,
    ) -> list[user_schema.SNSClientInfo]:
        stmt = sa.select(self.model).where(
            self.model.user_uuid == user_uuid,
            self.model.user_agent == sns_type.value,
            # 삭제되지 않았거나 만료되지 않은 토큰만 사용
            sa.or_(self.model.deleted_at.is_(None), self.model.expires_at > sa.func.now()),
        )
        return [
            user_schema.SNSClientInfo.model_validate_json(sns_history.client_token)
            for sns_history in self.get_multi_using_query(session=session, query=stmt)
        ]


userCRUD = UserCRUD(model=user_model.User)
userSignInHistoryCRUD = UserSignInHistoryCRUD(model=user_model.UserSignInHistory)
snsAuthInfoCRUD = SNSAuthInfoCRUD(model=user_model.UserSignInHistory)
