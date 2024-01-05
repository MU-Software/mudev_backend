import logging
import typing

import fastapi
import pydantic

import app.const.tag as tag_const

logger = logging.getLogger(__name__)
router = fastapi.APIRouter(prefix="/ssco", tags=[tag_const.OpenAPITag.YTDL])


class DummyResponse(pydantic.BaseModel):
    message: typing.Literal["ok"] = "ok"


@router.get("", response_model=DummyResponse)
async def ssco_telegram_webhook(request: fastapi.requests.Request) -> dict[str, str]:
    logger.warning("request.headers")
    logger.warning(request.headers)
    logger.warning("request.query_params")
    logger.warning(request.query_params)
    logger.warning("request.body")
    logger.warning(await request.body())
    return {"message": "ok"}
