from __future__ import annotations

import logging
import typing

import billiard.einfo
import celery
import celery.app.task
import celery.result
import sqlalchemy as sa

import app.config.celery as celery_config
import app.const.celery as celery_const
import app.db as db_module
import app.db.model.task as task_model
import app.redis as redis_module

logger = logging.getLogger(__name__)

T = typing.TypeVar("T")
EInfoType = typing.TypeVar("EInfoType", bound=billiard.einfo.ExceptionInfo)


class TaskModelType(typing.TypedDict):
    celery_task_name: typing.NotRequired[str]
    celery_task_id: typing.NotRequired[str]

    args: typing.NotRequired[tuple]
    kwargs: typing.NotRequired[dict]
    startable: typing.NotRequired[bool]

    state: typing.NotRequired[celery_const.CeleryTaskStatus]


class SessionTask(celery.Task, typing.Generic[T]):
    config_obj: celery_config.CelerySetting
    sync_db: db_module.SyncDB
    sync_redis: redis_module.SyncRedis

    track_started = True
    default_retry_delay = 60  # Retry after 1 minute.

    def __init__(self, *args: tuple, **kwargs: dict) -> None:
        super().__init__(*args, **kwargs)
        self.config_obj = celery_config.get_celery_setting()
        self.sync_db = db_module.SyncDB(config_obj=self.config_obj)
        self.sync_redis = redis_module.SyncRedis(config_obj=self.config_obj)

    @property
    def task_id(self) -> str | None:
        return typing.cast(str | None, typing.cast(celery.app.task.Context, self.request).id)

    @property
    def task_row(self) -> task_model.Task:
        if not self.task_id:
            raise RuntimeError("Task ID is not set")

        with self.sync_db.get_sync_session() as session:
            stmt = sa.select(task_model.Task).where(task_model.Task.celery_task_id == self.task_id)
            if not (row := session.execute(stmt).scalar_one_or_none()):
                row = task_model.Task(
                    celery_task_name=self.name,
                    celery_task_id=self.task_id,
                    args=self.request.args,
                    kwargs=self.request.kwargs,
                )
                session.add(row)
                session.commit()
            return row

    def update_task_row(self, **kwargs: typing.Unpack[TaskModelType]) -> None:
        with self.sync_db.get_sync_session() as session:
            task_row = self.task_row
            for key, value in kwargs.items():
                setattr(task_row, key, value)
            session.commit()

    @property
    def startable(self) -> bool:
        return self.task_row.startable

    @startable.setter
    def startable(self, value: bool) -> None:
        self.update_task_row(startable=value)

    def run(self, *args: tuple, **kwargs: dict) -> T:
        logger.info(f"Task[{self.task_id}] run called")
        return super().run(*args, **kwargs)

    def on_failure(self, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo: EInfoType) -> None:
        logger.info(f"Task[{task_id}] on_failure called")
        return super().on_failure(exc, self.task_id, args, kwargs, einfo)

    def on_retry(self, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo: EInfoType) -> None:
        logger.info(f"Task[{task_id}] on_retry called")
        return super().on_retry(exc, self.task_id, args, kwargs, einfo)

    def on_success(self, retval: T, task_id: str, args: tuple, kwargs: dict) -> None:
        logger.info(f"Task[{task_id}] on_success called")
        return super().on_success(retval, self.task_id, args, kwargs)

    def before_start(self, task_id: str, args: tuple, kwargs: dict) -> None:
        logger.info(f"Task[{task_id}] before_start called")
        return super().before_start(self.task_id, args, kwargs)

    def after_return(self, status: str, retval: T, task_id: str, args: tuple, kwargs: dict, einfo: EInfoType) -> None:
        logger.info(f"Task[{task_id}] after_return called: {status} (retval: {retval}, einfo: {einfo})")
        return super().after_return(status, retval, self.task_id, args, kwargs, einfo)

    def update_state(
        self,
        task_id: str | None = None,
        state: celery_const.CeleryTaskStatus | None = None,
        meta: dict | None = None,
        **kwargs: dict,
    ) -> None:
        logger.info(f"Task[{task_id}] state updated: {state} (meta: {meta})")
        self.update_task_row(state=state)
        return super().update_state(task_id=task_id, state=state, meta=meta, **kwargs)

    def apply_async(self, *args: tuple, **kwargs: dict) -> celery.result.AsyncResult:
        return super().apply_async(*args, **kwargs, task_id=self.task_id)
