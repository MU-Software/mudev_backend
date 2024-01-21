from __future__ import annotations

import contextlib
import dataclasses
import json
import re
import typing
import uuid

import fastapi
import redis
import sqlalchemy.ext.asyncio as sa_ext_asyncio
import telegram

import app.config.fastapi as fastapi_config
import app.const.sns as sns_const
import app.crud.user as user_crud
import app.dependency.common as common_dep
import app.util.fastapi as fastapi_util
import app.util.mu_string as string_util

CmdHandlerCallable = typing.Callable[
    [
        fastapi.Request,
        telegram.Update,
        fastapi_config.FastAPISetting,
        sa_ext_asyncio.AsyncSession,
        redis.Redis,
        uuid.UUID | None,
    ],
    typing.Awaitable[None],
]


@dataclasses.dataclass
class CommandHandler:
    pattern: re.Pattern | str
    title: str
    description: str
    require_auth: bool = False
    handler: CmdHandlerCallable | None = None
    show_in_help: bool = True


CmdHandlerMapType = dict[re.Pattern | str, CommandHandler]


def add_help_command(cmds: CmdHandlerMapType) -> CmdHandlerMapType:
    async def send_help_message(
        request: fastapi.Request,
        update: telegram.Update,
        config_obj: fastapi_config.FastAPISetting,
        db_session: sa_ext_asyncio.AsyncSession,
        redis_session: redis.Redis,
        user_uuid: uuid.UUID | None,
    ) -> None:
        help_text = "\n".join(f"{h.title}[{h.pattern}] : {h.description}" for h in cmds.values() if h.show_in_help)
        await update.effective_message.reply_text(text=help_text)

    cmd_helper = CommandHandler(
        pattern="/help",
        title="도움말",
        description="사용 가능한 명령어를 보여줍니다.",
        handler=send_help_message,
        show_in_help=False,
    )
    return cmds | {"/help": cmd_helper}


def is_handler_pattern_match(pattern: re.Pattern | str, in_str: str) -> bool:
    return (isinstance(pattern, str) and in_str.startswith(pattern)) or (
        isinstance(pattern, re.Pattern) and bool(pattern.match(in_str))
    )


def parse_request(request: str | bytes | dict | telegram.Update, bot: telegram.Bot | None) -> telegram.Update | None:
    if isinstance(request, telegram.Update):
        request.set_bot(bot)
        return request

    with contextlib.suppress(Exception):
        if isinstance(request, (bytes, str)):
            data: dict = json.loads(request)
        return telegram.Update.de_json(data, bot)
    return None


def register_telegram_webhook_handler(*, router: fastapi.APIRouter, route: str = "", cmds: CmdHandlerMapType) -> None:
    cmds = add_help_command(cmds)

    @router.post(route, response_model=fastapi_util.EmptyResponseSchema)
    async def webhook_handler(
        request: fastapi.Request,
        config_obj: common_dep.settingDI,
        db_session: common_dep.dbDI,
        redis_session: common_dep.redisDI,
    ) -> dict[str, str]:
        bot_token = config_obj.project.ssco.telegram_bot_token.get_secret_value()
        bot = telegram.Bot(token=bot_token)

        if not (payload := parse_request(await request.body(), bot)):
            raise fastapi.HTTPException(status_code=400, detail="읽은 메시지를 이해할 수 없어요.")

        if not ((msg_obj := payload.effective_message) and (msg_str := msg_obj.text)):
            await bot.send_message(chat_id=msg_obj.chat_id, text="메시지를 읽었지만, 할 수 있는 일이 적혀있지 않았어요.")
            raise fastapi.HTTPException(status_code=400, detail="메시지를 읽었지만, 할 수 있는 일이 적혀있지 않았어요.")

        msg_str = string_util.normalize(msg_str).strip()
        for pattern, handler in cmds.items():
            if is_handler_pattern_match(pattern, msg_str):
                if (user := payload.effective_user) and user.is_bot:
                    error_msg = "해당 사용자는 이 기능을 사용할 수 없습니다."
                    raise fastapi.HTTPException(status_code=401, detail=error_msg)

                user_uuid = await user_crud.snsAuthInfoCRUD.sns_user_to_user(
                    db_session,
                    sns_const.SNSAuthInfoUserAgentEnum.telegram,
                    user.id if user else None,
                )

                if handler.require_auth and not user_uuid:
                    error_msg = "기능을 사용하기 위해서는 먼저 mudev.cc의 계정과 연동을 해야합니다."
                    raise fastapi.HTTPException(status_code=403, detail=error_msg)

                await handler.handler(request, payload, config_obj, db_session, redis_session, user_uuid)
                return {"message": "ok"}

        await payload.effective_message.reply_text("무슨 말씀이신지 이해하지 못했어요, 다시 입력해주세요.")
        return {"message": "ok"}
