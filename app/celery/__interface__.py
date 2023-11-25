from __future__ import annotations

import contextlib
import enum
import logging
import typing
import uuid

import billiard.einfo
import celery
import celery.result
import redis
import sqlalchemy as sa
import sqlalchemy.exc as sa_exc
import sqlalchemy.orm as sa_orm
import sqlalchemy.pool as sa_pool

import app.config.celery as celery_config
import app.db.model.task as task_model

logger = logging.getLogger(__name__)
config_obj = celery_config.get_celery_setting()
T = typing.TypeVar("T")


class CeleryTaskStatus(enum.StrEnum):
    PENDING = enum.auto()
    STARTED = enum.auto()
    SUCCESS = enum.auto()
    FAILURE = enum.auto()
    RETRY = enum.auto()
    REVOKED = enum.auto()


class SessionTask(celery.Task, typing.Generic[T]):
    task_id: str

    redis_client: redis.Redis
    db_engine: sa.engine.Engine
    _db_session: sa_orm.Session | None = None

    track_started = True
    default_retry_delay = 60  # Retry after 1 minute.

    _task_instance: task_model.Task | None = None

    def __init__(self, *args: tuple, **kwargs: dict) -> None:
        super().__init__(*args, **kwargs)

        self.redis_client = redis.Redis.from_url(config_obj.redis.uri)
        self.redis_client.ping()
        self.db_engine = sa.create_engine(
            poolclass=sa_pool.NullPool,
            **config_obj.sqlalchemy.to_sqlalchemy_config(),
        )

        self.task_id = self.unused_task_id

    def _invalidate_session(self) -> None:
        if not self._db_session:
            return

        with contextlib.suppress(sa_exc.InvalidRequestError):
            self._db_session.commit()
        with contextlib.suppress(sa_exc.InvalidRequestError):
            self._db_session.rollback()
        self._db_session.invalidate()
        self._db_session = None

    @property
    def db_session(self) -> sa_orm.Session:
        if not (self._db_session and self._db_session.is_active):
            self._invalidate_session()
            self._db_session = sa_orm.Session(bind=self.db_engine)
            self._db_session.execute(sa.text("SELECT 1"))

        return self._db_session

    @property
    def unused_task_id(self) -> str:
        while True:
            task_id = f"{self.name}-{uuid.uuid4().hex}"
            stmt = sa.select(sa.exists(task_model.Task)).where(task_model.Task.celery_task_id == task_id)
            if not bool(self.db_session.execute(stmt).scalar_one_or_none()):
                return task_id

    @property
    def task_instance(self) -> task_model.Task:
        if self._task_instance is None:
            stmt = sa.select(task_model.Task).where(task_model.Task.celery_task_id == self.task_id)
            self._task_instance = self.db_session.execute(stmt).scalar_one_or_none()

        if self._task_instance is None:
            self._task_instance = task_model.Task(celery_task_name=self.name, celery_task_id=self.task_id)
            self.db_session.add(self._task_instance)
            self.db_session.commit()
            logger.info(f"Task[{self.task_id}] created")

        self.db_session.refresh(self._task_instance)
        return self._task_instance

    def run(self, *args: tuple, **kwargs: dict) -> T:
        logger.info(f"Task[{self.task_id}] run called")
        return super().run(*args, **kwargs)

    def on_failure(
        self, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo: billiard.einfo.ExceptionInfo
    ) -> None:
        logger.info(f"Task[{task_id}] on_failure called")
        self._invalidate_session()
        return super().on_failure(exc, self.task_id, args, kwargs, einfo)

    def on_retry(
        self, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo: billiard.einfo.ExceptionInfo
    ) -> None:
        logger.info(f"Task[{task_id}] on_retry called")
        self._invalidate_session()
        return super().on_retry(exc, self.task_id, args, kwargs, einfo)

    def on_success(self, retval: T, task_id: str, args: tuple, kwargs: dict) -> None:
        logger.info(f"Task[{task_id}] on_success called")
        return super().on_success(retval, self.task_id, args, kwargs)

    def before_start(self, task_id: str, args: tuple, kwargs: dict) -> None:
        logger.info(f"Task[{task_id}] before_start called")
        return super().before_start(self.task_id, args, kwargs)

    def after_return(
        self, status: str, retval: T, task_id: str, args: tuple, kwargs: dict, einfo: billiard.einfo.ExceptionInfo
    ) -> None:
        logger.info(f"Task[{task_id}] after_return called: {status} (retval: {retval}, einfo: {einfo})")
        self._invalidate_session()
        self.db_engine.dispose()
        return super().after_return(status, retval, self.task_id, args, kwargs, einfo)

    def update_state(
        self,
        task_id: str | None = None,
        state: CeleryTaskStatus | None = None,
        meta: dict | None = None,
        **kwargs: dict,
    ) -> None:
        logger.info(f"Task[{task_id}] state updated: {state} (meta: {meta})")

        if state == CeleryTaskStatus.SUCCESS:
            self.task_instance.done = True
            self.db_session.commit()
        return super().update_state(task_id=task_id, state=state, meta=meta, **kwargs)

    def apply_async(self, *args: tuple, **kwargs: dict) -> celery.result.AsyncResult:
        return super().apply_async(task_id=self.task_id, *args, **kwargs)
