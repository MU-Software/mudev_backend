import logging
import typing

import fastapi
import sqlalchemy as sa
import sqlalchemy.ext.asyncio as sa_ext_asyncio

import app.config.fastapi as fastapi_config
import app.db.__mixin__ as db_mixin
import app.db.model.user as user_model

logger = logging.getLogger(__name__)
config_obj = fastapi_config.get_fastapi_setting()
rdb_async_engine: sa_ext_asyncio.AsyncEngine
rdb_async_session_maker: sa_ext_asyncio.async_sessionmaker[sa_ext_asyncio.AsyncSession]


async def init_db():
    RESTAPI_VERSION = config_obj.restapi_version
    DROP_ALL_REFRESH_TOKEN_ON_LOAD = config_obj.drop_all_refresh_token_on_load
    SQLALCHEMY_SETTING = config_obj.sqlalchemy

    # Create DB engine and session pool.
    global rdb_async_engine, rdb_async_session_maker
    rdb_async_engine = sa_ext_asyncio.async_engine_from_config(
        configuration=SQLALCHEMY_SETTING.to_sqlalchemy_config(),
        prefix="",
    )
    rdb_async_engine.echo = True if RESTAPI_VERSION == "dev" else False
    rdb_async_session_maker = sa_ext_asyncio.async_sessionmaker(rdb_async_engine)

    async with rdb_async_session_maker() as session:
        # Check if DB is connected
        try:
            await session.execute(sa.text("SELECT 1"))
        except Exception as e:
            logger.critical(f"DB connection failed: {e}")
            raise e

        if RESTAPI_VERSION == "dev":
            # Create all tables only IF NOT EXISTS
            await session.run_sync(
                lambda _: db_mixin.DefaultModelMixin.metadata.create_all(
                    bind=rdb_async_engine.engine,
                    checkfirst=True,
                )
            )

            if DROP_ALL_REFRESH_TOKEN_ON_LOAD:
                # Drop sign-in history tables when on dev mode
                await session.execute(sa.delete(user_model.UserSignInHistory))
                await session.commit()


async def close_db_connection():
    # Close DB engine and session pool.
    global rdb_async_engine
    await rdb_async_engine.dispose()


# @contextlib.asynccontextmanager
async def get_db_session() -> sa_ext_asyncio.AsyncSession:
    global rdb_async_session_maker
    try:
        async with rdb_async_session_maker() as session:
            yield session
            await session.commit()
    except Exception as se:
        await session.rollback()
        raise se
    finally:
        await session.close()


dbDI = typing.Annotated[sa_ext_asyncio.AsyncSession, fastapi.Depends(get_db_session)]
