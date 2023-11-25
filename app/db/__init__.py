import logging

import sqlalchemy as sa
import sqlalchemy.ext.asyncio as sa_ext_asyncio

import app.config.fastapi as fastapi_config
import app.db.__mixin__ as db_mixin
import app.db.model.user as user_model

logger = logging.getLogger(__name__)
rdb_async_engine: sa_ext_asyncio.AsyncEngine
rdb_async_session_maker: sa_ext_asyncio.async_sessionmaker[sa_ext_asyncio.AsyncSession]


async def init_db() -> None:
    config_obj = fastapi_config.get_fastapi_setting()

    # Create DB engine and session pool.
    global rdb_async_engine, rdb_async_session_maker
    rdb_async_engine = sa_ext_asyncio.async_engine_from_config(
        configuration=config_obj.sqlalchemy.to_sqlalchemy_config(),
        prefix="",
    )
    rdb_async_engine.echo = True if config_obj.debug == "dev" else False
    rdb_async_session_maker = sa_ext_asyncio.async_sessionmaker(rdb_async_engine)

    async with rdb_async_session_maker() as session:
        # Check if DB is connected
        try:
            await session.execute(sa.text("SELECT 1"))
        except Exception as e:
            logger.critical(f"DB connection failed: {e}")
            raise e

        if config_obj.debug:
            # Create all tables only IF NOT EXISTS
            await session.run_sync(
                lambda _: db_mixin.DefaultModelMixin.metadata.create_all(
                    bind=rdb_async_engine.engine,
                    checkfirst=True,
                )
            )

            if config_obj.drop_all_refresh_token_on_load:
                # Drop sign-in history tables when on dev mode
                await session.execute(sa.delete(user_model.UserSignInHistory))
                await session.commit()


async def close_db_connection() -> None:
    # Close DB engine and session pool.
    global rdb_async_engine
    await rdb_async_engine.dispose()


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
