import contextlib
import typing

import celery
import fastapi
import fastapi.middleware.cors
import fastapi.staticfiles

import app.config.celery as celery_config
import app.config.fastapi as fastapi_config
import app.db as db_module
import app.error_handler as error_handler_module
import app.redis as redis_module
import app.route as route_module


def create_app(**kwargs: dict) -> fastapi.FastAPI:
    config_obj: fastapi_config.FastAPISetting = fastapi_config.get_fastapi_setting()

    @contextlib.asynccontextmanager
    async def app_lifespan(app: fastapi.FastAPI) -> typing.AsyncGenerator[None, None]:
        app.state.config_obj = config_obj
        app.state.async_db = db_module.AsyncDB(config_obj=config_obj)
        app.state.async_redis = redis_module.AsyncRedis(config_obj=config_obj)

        async with contextlib.AsyncExitStack() as async_stack:
            await async_stack.enter_async_context(app.state.async_db)  # type: ignore[arg-type]
            await async_stack.enter_async_context(app.state.async_redis)  # type: ignore[arg-type]
            yield

    if config_obj.sentry.is_sentry_available(mode="api"):
        import sentry_sdk

        sentry_sdk.init(**config_obj.sentry.build_config(mode="api"))

    app = fastapi.FastAPI(
        **kwargs | fastapi_config.get_fastapi_setting().to_fastapi_config(),
        lifespan=app_lifespan,
        exception_handlers=error_handler_module.get_error_handlers(),
        middleware=[
            fastapi.middleware.Middleware(
                fastapi.middleware.cors.CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            ),
        ],
    )
    app.mount("/static", fastapi.staticfiles.StaticFiles(directory="app/static"), name="static")
    for route in route_module.get_routes():
        app.include_router(route)

    celery_app = celery.Celery()
    celery_app.config_from_object(celery_config.get_celery_setting())

    return app
