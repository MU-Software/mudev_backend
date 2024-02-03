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
import app.const.error as error_const


@dataclasses.dataclass
class CommandHandlerContext:
    request: fastapi.Request
    payload: telegram.Update
    config: fastapi_config.FastAPISetting
    db_session: sa_ext_asyncio.AsyncSession
    redis_session: redis.Redis
    user_uuid: uuid.UUID | None
    handlers: dict[re.Pattern | str, CommandHandler]


@dataclasses.dataclass
class CommandHandler:
    pattern: re.Pattern | str
    title: str
    description: str
    handler: typing.Callable[[CommandHandlerContext], typing.Awaitable[None]]
    require_auth: bool = False
    show_in_help: bool = True


def send_msg_and_raise(update: telegram.Update, err: error_const.ErrorStruct) -> typing.NoReturn:
    if update.effective_message:
        update.effective_message.reply_text(err.msg)
    elif update.effective_chat:
        update.get_bot().send_message(chat_id=update.effective_chat.id, text=err.msg)
    err.raise_()


def is_handler_pattern_match(pattern: re.Pattern | str, in_str: str) -> bool:
    return (isinstance(pattern, str) and in_str.startswith(pattern)) or (
        isinstance(pattern, re.Pattern) and bool(pattern.match(in_str))
    )


def get_handler(cmds: dict[re.Pattern | str, CommandHandler], in_str: str) -> CommandHandler | None:
    for pattern, handler in cmds.items():
        if is_handler_pattern_match(pattern, in_str):
            return handler
    return None


def parse_request(request: str | bytes | dict | telegram.Update, bot: telegram.Bot | None) -> telegram.Update | None:
    if isinstance(request, telegram.Update):
        request.set_bot(bot)
        return request

    with contextlib.suppress(Exception):
        return telegram.Update.de_json(json.loads(request) if isinstance(request, (bytes, str)) else request, bot)
    return None
