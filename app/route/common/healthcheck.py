import logging
import typing

import fastapi
import pydantic
import sqlalchemy as sa

import app.const.tag as tag_const
import app.db as db_module
import app.redis as redis_module

logger = logging.getLogger(__name__)
router = fastapi.APIRouter()


class HealthCheckResponse(pydantic.BaseModel):
    message: typing.Literal["ok"] = "ok"


class ReadyzResponse(HealthCheckResponse):
    database: bool
    cache: bool


@router.get("/healthz", tags=[tag_const.OpenAPITag.HEALTH_CHECK], response_model=HealthCheckResponse)
async def healthz():
    return fastapi.responses.JSONResponse(content={"message": "ok"})


@router.get("/livez", tags=[tag_const.OpenAPITag.HEALTH_CHECK], response_model=HealthCheckResponse)
async def livez():
    return fastapi.responses.JSONResponse(content={"message": "ok"})


@router.get("/readyz", tags=[tag_const.OpenAPITag.HEALTH_CHECK], response_model=ReadyzResponse)
async def readyz(db_session: db_module.dbDI, redis_session: redis_module.redisDI):
    response = {"message": "ok", "database": False, "cache": False}
    try:
        await db_session.execute(sa.text("SELECT 1"))
        response["database"] = True
    except Exception:
        logger.exception("DB connection failed")

    try:
        redis_session.ping()
        response["cache"] = True
    except Exception:
        logger.exception("Redis connection failed")
    return fastapi.responses.JSONResponse(content=response)
