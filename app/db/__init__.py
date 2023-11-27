import contextlib
import logging
import typing

import sqlalchemy as sa
import sqlalchemy.ext.asyncio as sa_ext_asyncio
import sqlalchemy.orm as sa_orm

import app.config.fastapi as fastapi_config
import app.db.__mixin__ as db_mixin
import app.db.__type__ as db_type
import app.db.model.user as user_model
import app.util.mu_type as type_util

logger = logging.getLogger(__name__)


class SyncDB:
    config_obj: fastapi_config.FastAPISetting
    engine: sa.Engine | None = None
    session_maker: sa_orm.session.sessionmaker[sa_orm.session.Session] | None = None

    def __init__(self, config_obj: fastapi_config.FastAPISetting) -> None:
        self.config_obj = config_obj

    def open(self) -> None:
        # Create DB engine and session pool.
        config = self.config_obj.sqlalchemy.to_sqlalchemy_config()
        self.engine = sa.engine_from_config(configuration=config, prefix="")
        self.session_maker = sa_orm.session.sessionmaker(self.engine)

        with self.session_maker() as session:
            self.check_connection(session)
            self.create_all_tables(session)
            self.drop_all_refresh_token_on_load(session)

    def close(self) -> None:
        # Close DB engine and session pool.
        self.engine.dispose()
        self.engine = None

    def __enter__(self) -> typing.Self:
        self.open()
        return self

    def __exit__(self, *args: type_util.ContextExitArgType) -> None:
        self.close()

    async def __aenter__(self) -> typing.NoReturn:
        raise NotImplementedError("This method is not supported")

    async def __aexit__(self, *args: type_util.ContextExitArgType) -> typing.NoReturn:
        raise NotImplementedError("This method is not supported")

    @contextlib.contextmanager
    def get_session(self) -> typing.Generator[sa_orm.session.Session, None, None]:
        with self.session_maker() as session:
            try:
                yield session
                session.commit()
            except Exception as se:
                session.rollback()
                raise se
            finally:
                session.close()

    def check_connection(self, session: db_type.PossibleSessionType) -> None:
        """Check if DB is connected"""
        try:
            session.execute(sa.text("SELECT 1"))
        except Exception as e:
            logger.critical(f"DB connection failed: {e}")
            raise e

    def create_all_tables(self, session: db_type.PossibleSessionType) -> None:
        """Create all tables only IF NOT EXISTS on debug mode"""
        if self.config_obj.debug:
            db_mixin.DefaultModelMixin.metadata.create_all(bind=self.engine.engine, checkfirst=True)

    def drop_all_refresh_token_on_load(self, session: db_type.PossibleSessionType) -> None:
        """Drop sign-in history tables on debug mode"""
        if self.config_obj.debug:
            session.execute(sa.delete(user_model.UserSignInHistory))
            session.commit()


class AsyncDB(SyncDB):
    config_obj: fastapi_config.FastAPISetting
    engine: sa_ext_asyncio.AsyncEngine | None = None
    session_maker: sa_ext_asyncio.async_sessionmaker[sa_ext_asyncio.AsyncSession] | None = None

    def __init__(self, config_obj: fastapi_config.FastAPISetting) -> None:
        self.config_obj = config_obj

    async def open(self) -> None:  # type: ignore[override]
        # Create DB engine and session pool.
        config = self.config_obj.sqlalchemy.to_sqlalchemy_config()
        self.engine = sa_ext_asyncio.async_engine_from_config(configuration=config, prefix="")
        self.session_maker = sa_ext_asyncio.async_sessionmaker(self.engine, autoflush=False, expire_on_commit=False)

        async with self.session_maker() as session:
            await session.run_sync(self.check_connection)
            await session.run_sync(self.create_all_tables)
            await session.run_sync(self.drop_all_refresh_token_on_load)

    async def close(self) -> None:  # type: ignore[override]
        # Close DB engine and session pool.
        await self.engine.dispose()
        self.engine = None

    def __enter__(self) -> typing.NoReturn:  # type: ignore[override]
        raise NotImplementedError("This method is not supported")

    def __exit__(self, *args: type_util.ContextExitArgType) -> typing.NoReturn:  # type: ignore[override]
        raise NotImplementedError("This method is not supported")

    async def __aenter__(self) -> typing.Self:  # type: ignore[override]
        await self.open()
        return self

    async def __aexit__(self, *args: type_util.ContextExitArgType) -> None:  # type: ignore[override]
        await self.close()

    async def get_session(self) -> typing.AsyncGenerator[sa_ext_asyncio.AsyncSession, None]:  # type: ignore[override]
        async with self.session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception as se:
                await session.rollback()
                raise se
            finally:
                await session.close()


config_obj = fastapi_config.get_fastapi_setting()
sync_db, async_db = SyncDB(config_obj=config_obj), AsyncDB(config_obj=config_obj)
