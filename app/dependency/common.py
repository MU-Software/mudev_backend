import typing

import fastapi
import redis
import sqlalchemy.ext.asyncio as sa_ext_asyncio

import app.config.fastapi as fastapi_config
import app.db as db_module
import app.redis as redis_module

dbDI = typing.Annotated[sa_ext_asyncio.AsyncSession, fastapi.Depends(db_module.async_db.get_session)]
redisDI = typing.Annotated[redis.Redis, fastapi.Depends(redis_module.get_redis_session)]
settingDI = typing.Annotated[fastapi_config.FastAPISetting, fastapi.Depends(fastapi_config.get_fastapi_setting)]
