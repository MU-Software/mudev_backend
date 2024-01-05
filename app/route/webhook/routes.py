import fastapi

import app.const.tag as tag_const
import app.route.webhook.telegram.ssco

router = fastapi.APIRouter(prefix="/webhook", tags=[tag_const.OpenAPITag.WEBHOOK])
router.include_router(app.route.webhook.telegram.ssco.router, prefix="/telegram")
