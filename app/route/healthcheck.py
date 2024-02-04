import logging

import fastapi
import sqlalchemy as sa

import app.const.tag as tag_const
import app.dependency.common as common_dep
import app.dependency.header as header_dep
import app.util.fastapi as fastapi_util

logger = logging.getLogger(__name__)
router = fastapi.APIRouter(tags=[tag_const.OpenAPITag.HEALTH_CHECK])


class ReadyzResponse(fastapi_util.EmptyResponseSchema):
    debug: bool
    database: bool
    cache: bool


class AccessInfoResponse(fastapi_util.EmptyResponseSchema):
    user_agent: str
    user_ip: str


@router.get("/healthz", response_model=fastapi_util.EmptyResponseSchema, deprecated=True)
@router.get("/livez", response_model=fastapi_util.EmptyResponseSchema)
async def livez() -> dict[str, str]:
    return {"message": "ok"}


@router.get("/readyz", response_model=ReadyzResponse)
async def readyz(
    db_session: common_dep.dbDI, redis_session: common_dep.redisDI, config_obj: common_dep.settingDI
) -> dict[str, str | bool]:
    response: dict[str, str | bool] = {
        "message": "ok",
        "debug": config_obj.debug,
        "database": False,
        "cache": False,
    }

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
    return response


@router.get("/access_info", response_model=AccessInfoResponse)
async def access_info(
    user_ip: header_dep.user_ip = None,
    user_agent: header_dep.user_agent = None,
) -> dict[str, str | None]:
    return {"user_agent": user_agent, "user_ip": user_ip}
