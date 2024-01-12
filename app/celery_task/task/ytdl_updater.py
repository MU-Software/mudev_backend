import logging
import subprocess as sp  # nosec B404
import time

import celery
import sqlalchemy as sa

import app.celery_task.__interface__ as celery_interface
import app.const.celery as celery_const
import app.db.model.task as task_model

logger = logging.getLogger(__name__)


@celery.shared_task(bind=True, base=celery_interface.SessionTask)
def ytdl_updater_task(self: celery_interface.SessionTask[None]) -> None:
    import app.celery_task.task.ytdl as ytdl

    ytdl_downloader_task_name: str = ytdl.ytdl_downloader_task.name

    # 만약 현재 끝나지 않은 ytdl downloader task가 있다면, 모두 종료될 때까지 대기합니다.
    stmt = sa.select(sa.exists(task_model.Task)).where(
        task_model.Task.celery_task_name == ytdl_downloader_task_name,
        task_model.Task.startable.is_(True),
        task_model.Task.state != celery_const.CeleryTaskStatus.SUCCESS,
    )
    with self.sync_db.get_sync_session() as session:
        while bool(session.execute(stmt).scalar_one_or_none()):
            time.sleep(5)

    # subprocess로 poetry update youtube-dl 실행
    proc = sp.Popen(["poetry", "update", "yt_dlp"], stdout=sp.PIPE, stderr=sp.STDOUT)  # nosec B603 B607
    with proc.stdout:
        for line in iter(proc.stdout.readline, b""):
            logger.info("YTDLUpadterTask SP: %r", line)

    if return_code := proc.wait():
        err_msg = f"[poetry update yt_dlp] failed - returncode: {return_code}"
        logger.error(err_msg)
        raise RuntimeError(err_msg)

    # Pending된 task를 전부 실행 가능 상태로 변경합니다.
    stmt = sa.update(task_model.Task).where(
        task_model.Task.celery_task_name == ytdl_downloader_task_name,
        task_model.Task.startable.is_(False),
        task_model.Task.state != celery_const.CeleryTaskStatus.SUCCESS,
    )
    with self.sync_db.get_sync_session() as session:
        session.execute(stmt)
        session.commit()
