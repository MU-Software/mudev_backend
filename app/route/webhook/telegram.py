import logging
import uuid

import fastapi
import redis
import sqlalchemy.ext.asyncio as sa_ext_asyncio
import telegram

import app.celery_task.task.ytdl as ytdl_task
import app.config.fastapi as fastapi_config
import app.const.sns as sns_const
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
        "본 봇은 먼저 mudev.cc의 계정과 연동한 후 사용하실 수 있습니다.\n/auth 을 누르거나 입력하셔서 인증을 진행해주세요."
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
    if not (sns_user := update.effective_user):
        raise fastapi.HTTPException(status_code=422, detail="유저 정보를 얻을 수 없었습니다.")
    if not (sns_msg := update.effective_message):
        raise fastapi.HTTPException(status_code=422, detail="메시지에서 정보를 얻을 수 없었습니다.")
    sns_chat = sns_msg.chat

    sns_type = sns_const.SNSAuthInfoUserAgentEnum.telegram.value
    sns_token = user_schema.SNSClientInfo(sns_type=sns_type, user_id=sns_user.id, chat_id=sns_chat).model_dump_json()
    sns_info = user_schema.SNSAuthInfo(user_agent=sns_type, client_token=sns_token)

    key = config_obj.secret_key.get_secret_value()
    url = config_obj.frontend_name + "/user/sns?sns_token=" + sns_info.to_token(key)
    await update.effective_message.reply_text(
        text="아래 버튼을 눌러 mudev.cc 계정 연동을 진행해주세요.",
        reply_markup=telegram.InlineKeyboardMarkup([[telegram.InlineKeyboardButton(text="mudev.cc 인증", url=url)]]),
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
        await update.effective_message.reply_text(text="유효한 YouTube URL이 아니에요.")
        return None

    video_create_obj = ssco_schema.VideoCreate(youtube_vid=youtube_id)
    video_record, created = await ssco_crud.videoCRUD.get_or_create_async(db_session, video_create_obj)
    video_record.users.add(await user_crud.userCRUD.get(db_session, uuid=user_uuid))
    await db_session.commit()

    if created:
        ytdl_task.ytdl_downloader_task.delay(youtube_vid=youtube_id)


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
