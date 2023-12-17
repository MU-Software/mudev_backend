import contextlib
import datetime
import pathlib as pt
import typing

import IPython
import IPython.terminal.ipapp
import pydantic
import sqlalchemy as sa

import app.config.fastapi as fastapi_config
import app.db as db_module
import app.db.model as db_model
import app.redis as redis_module

DEFAULT_IMPORT_NAMESPACE = {
    **db_model.__dict__,
    "datetime": datetime,
    "pt": pt,
    "typing": typing,
    "pydantic": pydantic,
    "sa": sa,
}


def py_shell() -> None:
    """IPython shell을 실행합니다."""
    config_obj = fastapi_config.get_fastapi_setting()
    sync_db = db_module.SyncDB(config_obj=config_obj)
    sync_redis = redis_module.SyncRedis(config_obj=config_obj)

    with contextlib.ExitStack() as init_stack:
        init_stack.enter_context(sync_db)  # type: ignore[arg-type]
        init_stack.enter_context(sync_redis)  # type: ignore[arg-type]

        with contextlib.ExitStack() as ipy_stack:
            ipy_namespace = DEFAULT_IMPORT_NAMESPACE | {
                "config": config_obj,
                "db_session": ipy_stack.enter_context(sync_db.get_sync_session()),
                "redis_session": ipy_stack.enter_context(sync_redis.get_sync_session()),
            }

            IPython.start_ipython(argv=[], user_ns=ipy_namespace)


cli_patterns: list[typing.Callable] = [py_shell]
