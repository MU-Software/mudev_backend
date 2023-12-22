from __future__ import annotations

import contextlib
import logging
import typing
import uuid

import billiard.einfo
import celery
import celery.result
import sqlalchemy as sa
import sqlalchemy.orm as sa_orm

import app.config.celery as celery_config
import app.const.celery as celery_const
import app.db as db_module
import app.db.model.task as task_model
import app.redis as redis_module

logger = logging.getLogger(__name__)

T = typing.TypeVar("T")
EInfoType = typing.TypeVar("EInfoType", bound=billiard.einfo.ExceptionInfo)


class SessionTask(celery.Task, typing.Generic[T]):
    task_id: str

    config_obj: celery_config.CelerySetting
    sync_db: db_module.SyncDB
    sync_redis: redis_module.SyncRedis

    track_started = True
    default_retry_delay = 60  # Retry after 1 minute.

    _db_session: sa_orm.Session | None = None
    _task_instance: task_model.Task | None = None

    def __init__(self, *args: tuple, **kwargs: dict) -> None:
        super().__init__(*args, **kwargs)
        self.config_obj = celery_config.get_celery_setting()
        self.sync_db = db_module.SyncDB(config_obj=self.config_obj)
        self.sync_redis = redis_module.SyncRedis(config_obj=self.config_obj)

        self.task_id = self.unused_task_id

    @property
    @contextlib.contextmanager
    def db_session(self) -> typing.Generator[sa_orm.Session, None, None]:
        # This is a blocker for multiple session creation.
        if self._db_session:
            yield self._db_session
        else:
            with self.sync_db as db:
                with db.get_sync_session() as session:
                    self._db_session = session
                    yield self._db_session

    @property
    def unused_task_id(self) -> str:
        with self.db_session as session:
            while True:
                task_id = f"{self.name}-{uuid.uuid4().hex}"
                stmt = sa.select(sa.exists(task_model.Task)).where(task_model.Task.celery_task_id == task_id)
                if not bool(session.execute(stmt).scalar_one_or_none()):
                    return task_id

    @property
    def task_instance(self) -> task_model.Task:
        with self.db_session as session:
            if self._task_instance is None:
                stmt = sa.select(task_model.Task).where(task_model.Task.celery_task_id == self.task_id)
                self._task_instance = session.execute(stmt).scalar_one_or_none()

            if self._task_instance is None:
                self._task_instance = task_model.Task(celery_task_name=self.name, celery_task_id=self.task_id)
                session.add(self._task_instance)
                session.commit()
                logger.info(f"Task[{self.task_id}] created")

            session.refresh(self._task_instance)
        return self._task_instance

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

        with self.db_session as session:
            if state:
                self.task_instance.state = state
                session.commit()

        return super().update_state(task_id=task_id, state=state, meta=meta, **kwargs)

    def apply_async(self, *args: tuple, **kwargs: dict) -> celery.result.AsyncResult:
        return super().apply_async(*args, **kwargs, task_id=self.task_id)
