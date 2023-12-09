import contextlib
import logging
import typing

import pydantic
import redis

import app.util.mu_type as type_util

logger = logging.getLogger(__name__)


class RedisConfigDescriptor(typing.Protocol):
    class RedisPyConfigDescriptor(typing.Protocol):
        dsn: pydantic.RedisDsn
        uri: str | None

    debug: bool
    redis: RedisPyConfigDescriptor


class Redis:
    config_obj: RedisConfigDescriptor
    connection_pool: redis.ConnectionPool | None = None

    def check_connection(self, session: redis.Redis) -> None:
        """Check if redis is connected"""
        try:
            session.ping()
        except Exception as e:
            logger.critical(f"Redis connection failed: {e}")
            raise e

    def flush_all_keys(self, session: redis.Redis) -> None:
        """Flush all keys on debug mode"""
        if self.config_obj.debug:
            session.flushdb()


class SyncRedis(Redis, type_util.SyncConnectedResource):
    def open(self) -> typing.Self:
        # Create redis connection pool.
        self.connection_pool = redis.ConnectionPool.from_url(url=self.config_obj.redis.uri)

        with redis.Redis(connection_pool=self.connection_pool) as client:
            self.check_connection(client)
            self.flush_all_keys(client)

        return self

    def close(self) -> None:
        self.connection_pool.disconnect(inuse_connections=True)

    @contextlib.contextmanager
    def get_sync_session(self) -> typing.Generator[redis.Redis, None, None]:
        with redis.Redis(connection_pool=self.connection_pool) as session:
            yield session


class AsyncRedis(Redis, type_util.AsyncConnectedResource):
    """
    Redis connection pool wrapper for async.
    Actually, this class does not support async properly, as it uses sync redis client.
    (AsyncRedis is just for using with FastAPI dependency injection.)
    But it is enough for now.
    """

    async def aopen(self) -> typing.Self:
        # Create redis connection pool.
        self.connection_pool = redis.ConnectionPool.from_url(url=self.config_obj.redis.uri)

        with redis.Redis(connection_pool=self.connection_pool) as client:
            self.check_connection(client)
            self.flush_all_keys(client)

        return self

    async def aclose(self) -> None:
        self.connection_pool.disconnect(inuse_connections=True)

    @contextlib.asynccontextmanager
    async def get_async_session(self) -> typing.AsyncGenerator[redis.Redis, None]:  # type: ignore[override]
        # TODO: FIXME: Fix mypy ignored error.
        with redis.Redis(connection_pool=self.connection_pool) as session:
            yield session
