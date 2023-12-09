import datetime
import typing

import argon2
import fastapi
import redis
import sqlalchemy as sa
import sqlalchemy.ext.asyncio as sa_ext_asyncio

import app.config.fastapi as fastapi_config
import app.db as db_module
import app.db.model.user as user_model
import app.redis as redis_module


def fastapi_setting_di(request: fastapi.Request) -> typing.Generator[fastapi_config.FastAPISetting, None, None]:
    fastapi_app: fastapi.FastAPI = request.app
    config_obj: fastapi_config.FastAPISetting = fastapi_app.state.config_obj
    yield config_obj


async def async_db_session_di(request: fastapi.Request) -> typing.AsyncGenerator[sa_ext_asyncio.AsyncSession, None]:
    fastapi_app: fastapi.FastAPI = request.app
    async_db: db_module.AsyncDB = fastapi_app.state.async_db
    async with async_db.get_async_session() as session:
        yield session


async def async_redis_session_di(request: fastapi.Request) -> typing.AsyncGenerator[redis.Redis, None]:
    fastapi_app: fastapi.FastAPI = request.app
    async_redis: redis_module.AsyncRedis = fastapi_app.state.async_redis
    async with async_redis.get_async_session() as session:
        yield session


dbDI = typing.Annotated[sa_ext_asyncio.AsyncSession, fastapi.Depends(async_db_session_di)]
redisDI = typing.Annotated[redis.Redis, fastapi.Depends(async_redis_session_di)]
settingDI = typing.Annotated[fastapi_config.FastAPISetting, fastapi.Depends(fastapi_setting_di)]


async def get_system_user(db_session: dbDI, config_obj: settingDI) -> user_model.User:
    stmt = sa.select(user_model.User).where(user_model.User.username == "system")
    if not (system_user := await db_session.scalar(stmt)):
        system_user = user_model.User(
            username="system",
            password=argon2.PasswordHasher().hash(config_obj.secret_key),
            email="system@mudev.cc",
            email_verified_at=sa.func.now(),
            nickname="system",
            private=True,
            birth=datetime.date.min,
        )
        db_session.add(system_user)
        await db_session.commit()

    return system_user


system_user_di = typing.Annotated[user_model.User, fastapi.Depends(get_system_user)]
