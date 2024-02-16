import logging
import re
import typing

import fastapi
import pydantic
import sqlalchemy as sa
import telegram

import app.celery_task.task.ytdl as ytdl_task
import app.const.error as error_const
import app.const.sns as sns_const
import app.const.tag as tag_const
import app.crud.ssco as ssco_crud
import app.crud.user as user_crud
import app.db.model.ssco as ssco_model
import app.dependency.common as common_dep
import app.schema.ssco as ssco_schema
import app.schema.user as user_schema
import app.util.ext_api.telegram as telegram_util
import app.util.ext_api.youtube as youtube_util
import app.util.fastapi as fastapi_util
import app.util.mu_string as string_util

logger = logging.getLogger(__name__)
router = fastapi.APIRouter(prefix="/webhook/telegram", tags=[tag_const.OpenAPITag.YTDL])


async def send_help(ctx: telegram_util.CommandHandlerContext) -> None:
    help_text = "\n".join(f"{h.title}[{h.pattern}] : {h.description}" for h in ctx.handlers.values() if h.show_in_help)
    await ctx.payload.effective_message.reply_text(text=help_text)


async def start(ctx: telegram_util.CommandHandlerContext) -> None:
    msg = "본 봇은 먼저 mudev.cc의 계정과 연동한 후 사용하실 수 있습니다.\n/auth 을 누르거나 입력하셔서 인증을 진행해주세요."
    await ctx.payload.effective_message.reply_text(msg)


async def auth_user(ctx: telegram_util.CommandHandlerContext) -> None:
    if ctx.user_uuid:
        telegram_util.send_msg_and_raise(ctx.payload, error_const.TelegramError.USER_ALREADY_SYNCED())

    sns_user = typing.cast(telegram.User, ctx.payload.effective_user)
    sns_chat = ctx.payload.effective_message.chat.id

    sns_type = sns_const.SNSAuthInfoUserAgentEnum.telegram.value
    sns_token = user_schema.SNSClientInfo(sns_type=sns_type, user_id=sns_user.id, chat_id=sns_chat).model_dump_json()
    sns_info = user_schema.SNSAuthInfo(user_agent=sns_type, client_token=sns_token)

    key = ctx.config.secret_key.get_secret_value()
    url = f"{ctx.config.project.frontend_domain}/user/sns?sns_token={sns_info.to_token(key)}"
    btn_markup = telegram.InlineKeyboardMarkup([[telegram.InlineKeyboardButton(text="mudev.cc 인증", url=url)]])
    await ctx.payload.effective_message.reply_text(
        text="아래 버튼을 눌러 mudev.cc 계정 연동을 진행해주세요.", reply_markup=btn_markup
    )


async def create_ytdl_task(ctx: telegram_util.CommandHandlerContext) -> None:
    message: telegram.Message = ctx.payload.effective_message
    if not (youtube_id := youtube_util.extract_vid_from_url(message.text)):
        await message.reply_text(text="유효한 YouTube URL이 아니에요.")
        return None

    stmt = sa.select(ssco_model.Video).where(ssco_model.Video.youtube_vid == youtube_id)
    if not (video_record := await ssco_crud.videoCRUD.get_using_query(ctx.db_session, stmt)):
        video_create_obj = ssco_schema.VideoCreate(youtube_vid=youtube_id)
        video_record = await ssco_crud.videoCRUD.create(ctx.db_session, obj_in=video_create_obj)
        ytdl_task.ytdl_downloader_task.delay(youtube_vid=youtube_id)

    await ctx.db_session.refresh(video_record, attribute_names=["users", "files"])
    video_record.users.add(await user_crud.userCRUD.get(ctx.db_session, uuid=ctx.user_uuid))
    await ctx.db_session.commit()

    if video_record.files:
        btn_markup = telegram.InlineKeyboardMarkup(
            [
                [
                    telegram.InlineKeyboardButton(
                        text=f"{file.mimetype} 파일 다운로드",
                        url=f"{ctx.config.project.backend_domain}/file/{file.uuid}/download/",
                    )
                ]
                for file in video_record.files
            ]
        )
        message.reply_text(text=f"영상이 준비됐어요!\n{video_record.title}", reply_markup=btn_markup)
        return None

    message.reply_text(text="영상을 내려받는 중이에요,\n잠시만 기다려주세요...\n(완료되면 따로 알림을 드릴게요.)")
    return None


cmds: dict[re.Pattern | str, telegram_util.CommandHandler] = {
    "/start": telegram_util.CommandHandler(
        pattern="/start",
        title="start",
        description="봇과의 채팅을 시작합니다.",
        handler=start,
    ),
    "/auth": telegram_util.CommandHandler(
        pattern="/auth",
        title="계정 연동",
        description="mudev.cc의 계정과 연동합니다.",
        handler=auth_user,
    ),
    "/help": telegram_util.CommandHandler(
        pattern="/help",
        title="도움말",
        description="사용 가능한 명령어를 보여줍니다.",
        handler=send_help,
        show_in_help=False,
    ),
    youtube_util.VIDEO_REGEX: telegram_util.CommandHandler(
        pattern=youtube_util.VIDEO_REGEX,
        title="유튜브 영상 다운로드",
        description="유튜브 영상을 다운로드합니다.",
        handler=create_ytdl_task,
        require_auth=True,
        show_in_help=False,
    ),
}


@router.post("", response_model=fastapi_util.EmptyResponseSchema)
async def webhook_handler(
    request: fastapi.Request,
    config_obj: common_dep.settingDI,
    db_session: common_dep.dbDI,
    redis_session: common_dep.redisDI,
) -> dict[str, str]:
    bot_token = config_obj.project.ssco.telegram_bot_token.get_secret_value()
    bot = telegram.Bot(token=bot_token)

    if not (payload := telegram_util.parse_request(await request.body(), bot)):
        error_const.ClientError.REQUEST_BODY_EMPTY().raise_()
    if not ((msg_obj := payload.effective_message) and (msg_str := msg_obj.text)):
        telegram_util.send_msg_and_raise(payload, error_const.TelegramError.MESSAGE_NOT_GIVEN())
    if not (user := payload.effective_user):
        telegram_util.send_msg_and_raise(payload, error_const.TelegramError.USER_NOT_GIVEN())
    if user.is_bot:
        telegram_util.send_msg_and_raise(payload, error_const.AuthZError.BOT_USER_NOT_ALLOWED())

    if not (handler := telegram_util.get_handler(cmds, string_util.normalize(msg_str).strip())):
        telegram_util.send_msg_and_raise(payload, error_const.TelegramError.HANDLER_NOT_MATCH())

    sns_type = sns_const.SNSAuthInfoUserAgentEnum.telegram
    try:
        sns_token = user_schema.SNSClientInfo(
            sns_type=sns_type, user_id=user.id, chat_id=msg_obj.chat.id
        ).model_dump_json()
    except pydantic.ValidationError:
        sns_token = None
    user_uuid = await user_crud.snsAuthInfoCRUD.sns_token_to_user(db_session, sns_type, sns_token)

    if handler.require_auth and not user_uuid:
        telegram_util.send_msg_and_raise(payload, error_const.AuthZError.REQUIRES_ACCOUNT_SYNC())

    await handler.handler(
        telegram_util.CommandHandlerContext(
            request=request,
            payload=payload,
            config=config_obj,
            db_session=db_session,
            redis_session=redis_session,
            user_uuid=user_uuid,
            handlers=cmds,
        )
    )
    return {"message": "ok"}
