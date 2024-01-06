import logging
import uuid

import fastapi
import redis
import sqlalchemy.ext.asyncio as sa_ext_asyncio
import telegram

import app.celery_task.task.ytdl as ytdl_task
import app.config.fastapi as fastapi_config
import app.const.tag as tag_const
import app.crud.ssco as ssco_crud
import app.crud.user as user_crud
import app.schema.ssco as ssco_schema
import app.schema.user as user_schema
import app.util.ext_api.telegram as telegram_util
import app.util.ext_api.youtube as youtube_util

logger = logging.getLogger(__name__)
router = fastapi.APIRouter(prefix="/webhook/telegram", tags=[tag_const.OpenAPITag.YTDL])


async def start(
    request: fastapi.Request,
    update: telegram.Update,
    config_obj: fastapi_config.FastAPISetting,
    db_session: sa_ext_asyncio.AsyncSession,
    redis_session: redis.Redis,
    user_uuid: uuid.UUID | None,
) -> None:
    await update.effective_message.reply_text(
        "본 봇을 사용하기 위해서는 먼저 mudev.cc의 계정과 연동을 해야합니다.\n/auth 을 누르거나 입력하셔서 인증을 진행해주세요."
    )


async def auth_user(
    request: fastapi.Request,
    update: telegram.Update,
    config_obj: fastapi_config.FastAPISetting,
    db_session: sa_ext_asyncio.AsyncSession,
    redis_session: redis.Redis,
    user_uuid: uuid.UUID | None,
) -> None:
    if user_uuid:
        await update.effective_message.reply_text("이미 연동된 계정이 있습니다.")
        raise fastapi.HTTPException(status_code=409, detail="이미 연동된 계정이 있습니다.")
    if not (telegram_user := update.effective_user):
        raise fastapi.HTTPException(status_code=422, detail="유저 정보를 얻을 수 없었습니다.")

    sns_type = user_schema.SNSAuthInfoUserAgentEnum.telegram.name
    sns_info = user_schema.SNSAuthInfo(user_agent=sns_type, client_token=telegram_user.id)
    key = config_obj.secret_key.get_secret_value()
    await update.effective_message.reply_text(
        text="mudev.cc의 계정과 연동을 위해 아래 링크를 클릭해주세요.",
        reply_markup=telegram.InlineKeyboardMarkup(
            [
                [
                    telegram.InlineKeyboardButton(
                        text="mudev.cc 인증", url=str(request.base_url) + "/user/sns?sns_token=" + sns_info.to_token(key)
                    )
                ],
            ],
        ),
    )


async def create_ytdl_task(
    request: fastapi.Request,
    update: telegram.Update,
    config_obj: fastapi_config.FastAPISetting,
    db_session: sa_ext_asyncio.AsyncSession,
    redis_session: redis.Redis,
    user_uuid: uuid.UUID | None,
) -> None:
    if not (message := update.effective_message):
        raise fastapi.HTTPException(status_code=422, detail="메시지에서 정보를 얻을 수 없었습니다.")

    if not (youtube_id := youtube_util.extract_vid_from_url(message.text)):
        raise fastapi.HTTPException(status_code=422, detail="유효한 유튜브 URL이 아닙니다.")

    video_create_obj = ssco_schema.VideoCreate(youtube_vid=youtube_id)
    video_record, created = await ssco_crud.videoCRUD.get_or_create_async(db_session, video_create_obj)
    await db_session.refresh(video_record, ["users"])
    video_record.users.add(await user_crud.userCRUD.get(db_session, uuid=user_uuid))
    await db_session.commit()

    if created:
        ytdl_task.ytdl_downloader_task.delay(video_id=youtube_id)


telegram_util.register_telegram_webhook_handler(
    router=router,
    route="/ssco",
    cmds={
        "/start": telegram_util.CommandHandler(
            pattern="/start",
            title="start",
            description="봇과의 채팅을 시작합니다.",
            handler=start,
        ),
        "/auth": telegram_util.CommandHandler(
            pattern="/auth",
            title="계정 연동",
            description="mudev.cc의 계정과 연동을 시작합니다.",
            handler=auth_user,
        ),
        youtube_util.VIDEO_REGEX: telegram_util.CommandHandler(
            pattern=youtube_util.VIDEO_REGEX,
            title="유튜브 영상 다운로드",
            description="유튜브 영상을 다운로드합니다.",
            show_in_help=False,
            handler=create_ytdl_task,
        ),
    },
)
