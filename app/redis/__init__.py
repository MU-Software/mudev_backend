import logging

import redis

import app.config.fastapi as fastapi_config

logger = logging.getLogger(__name__)
config_obj = fastapi_config.get_fastapi_setting()
redis_connection_pool: redis.ConnectionPool = None


async def init_redis() -> None:
    # Create redis connection pool.
    global redis_connection_pool
    redis_connection_pool = redis.ConnectionPool.from_url(url=config_obj.redis.uri)

    with redis.Redis(connection_pool=redis_connection_pool) as client:
        try:
            if not client.ping():
                raise Exception("Cannot connect to redis server")

            if config_obj.debug and config_obj.drop_all_refresh_token_on_load:
                # If DROP_ALL_REFRESH_TOKEN_ON_LOAD is set, flush all keys in redis DB
                logger.warning("Flushing all keys in redis DB")
                client.flushdb()  # no asynchronous
        except Exception as e:
            logger.error(f"Redis initialization failed: {e}")
            raise e


async def close_redis_connection() -> None:
    redis_connection_pool.disconnect()


async def get_redis_session() -> redis.Redis:
    return redis.Redis(connection_pool=redis_connection_pool)
