import celery
import fastapi
import fastapi.middleware.cors
import fastapi.staticfiles

import app.config.celery as celery_config
import app.config.fastapi as fastapi_config
import app.db as db_module
import app.redis as redis_module
import app.route.common.healthcheck as healthcheck_route
import app.route.common.user as user_route

fastapi_config_obj = fastapi_config.get_fastapi_setting()
celery_config_obj = celery_config.get_celery_setting()


async def on_app_startup() -> None:
    await db_module.init_db()
    await redis_module.init_redis()


async def on_app_shutdown() -> None:
    await db_module.close_db_connection()
    await redis_module.close_redis_connection()


def create_app(**kwargs: dict) -> fastapi.FastAPI:
    app = fastapi.FastAPI(
        **kwargs,
        **fastapi_config_obj.to_fastapi_config(),
        on_startup=[on_app_startup],
        on_shutdown=[on_app_shutdown],
        middleware=[
            fastapi.middleware.Middleware(
                fastapi.middleware.cors.CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            ),
        ]
    )
    app.mount("/static", fastapi.staticfiles.StaticFiles(directory="app/static"), name="static")
    app.include_router(healthcheck_route.router)
    app.include_router(user_route.router)

    celery_app = celery.Celery()
    celery_app.config_from_object(celery_config_obj)

    return app
