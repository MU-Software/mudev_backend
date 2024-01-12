import logging
import pathlib as pt
import typing
import uuid

import celery
import ffmpeg
import sqlalchemy as sa

import app.celery_task.__interface__ as celery_interface
import app.const.celery as celery_const
import app.crud.file as file_crud
import app.crud.ssco as ssco_crud
import app.crud.user as user_crud
import app.db.model.file as file_model
import app.db.model.ssco as ssco_model
import app.db.model.task as task_model
import app.schema.file as file_schema
import app.schema.ssco as ssco_schema
import app.util.ext_api.youtube as youtube_util

logger = logging.getLogger(__name__)


class FileInfo(typing.TypedDict):
    path: pt.Path | None
    uuid: uuid.UUID | None


def raise_if_task_not_runnable(task: celery_interface.SessionTask) -> None:
    """
    ytdl_updater task가 실행 중인지 확인 후,
    updater가 실행 중이면 본 Task를 실패로 처리하고 5분 후에 다시 시도합니다.
    """
    retry_kwargs = {
        "countdown": 5 * 60,
        "max_retries": task.max_retries + 1 if task.max_retries is not None else 1,
        "throw": True,
    }
    if not task.startable:
        raise task.retry(**retry_kwargs, exc=RuntimeError("Task is not startable"))

    import app.celery_task.task.ytdl_updater as ytdl_updater

    ytdl_updater_task_name: str = ytdl_updater.ytdl_updater_task.name
    stmt = sa.select(sa.exists(task_model.Task)).where(
        task_model.Task.celery_task_name == ytdl_updater_task_name,
        task_model.Task.startable.is_(True),
        task_model.Task.state != celery_const.CeleryTaskStatus.SUCCESS,
    )
    with task.sync_db.get_sync_session() as session:
        if bool(session.execute(stmt).scalar_one_or_none()):
            task.update_task_row(startable=False)
            raise task.retry(**retry_kwargs, exc=RuntimeError("Updater is running"))


def convert_video_to_m4a_and_mp3(video_path: pt.Path, coverart_path: pt.Path) -> dict[str, pt.Path]:
    """ffmpeg를 이용해 영상 파일을 m4a와 mp3 파일로 변환"""
    mp3_path = video_path.with_suffix(".mp3")
    m4a_path = video_path.with_suffix(".m4a")

    original_file_node = ffmpeg.input(video_path)
    audio_node = original_file_node.audio.filter("silenceremove", "1", "0", "-50dB").filter_multi_output("asplit")
    m4a_output_node = audio_node.stream(1).output(m4a_path.as_posix())
    mp3_output_node = (
        audio_node.stream(0)
        .output(ffmpeg.input(coverart_path), mp3_path.as_posix())
        .global_args("-disposition:0", "attached_pic")
        .global_args("-id3v2_version", "3")
    )
    ffmpeg.merge_outputs(mp3_output_node, m4a_output_node).run(overwrite_output=True)

    return {"mp3": mp3_path, "m4a": m4a_path}


@celery.shared_task(bind=True, base=celery_interface.SessionTask)
def ytdl_downloader_task(self: celery_interface.SessionTask[None], *, video_id: str) -> None:
    """youtube-dl을 이용해 비디오를 다운로드하고, Video와 File row를 생성합니다."""
    raise_if_task_not_runnable(self)

    save_dir = self.config_obj.project.upload_to.youtube_video_dir(video_id)
    download_info = youtube_util.download_video(video_id, save_dir)

    file_paths: dict[str, pt.Path] = {}
    file_paths["video"] = download_info.file_path
    file_paths["thumbnail"] = youtube_util.download_thumbnail(video_id, save_dir)

    audio_paths = convert_video_to_m4a_and_mp3(file_paths["video"], file_paths["thumbnail"])
    file_paths |= audio_paths

    with self.sync_db.get_sync_session() as session:
        system_user = user_crud.userCRUD.get_system_user(session)
        file_records: dict[str, file_model.File] = {
            file_type: file_crud.fileCRUD.create(
                session,
                obj_in=file_schema.FileCreate(path=path, created_by_uuid=system_user.uuid),
            )
            for file_type, path in file_paths.items()
        }

        video_obj_kwargs = {
            "title": download_info.title,
            "thumbnail_uuid": file_records["thumbnail"].uuid,
            "data": download_info.dumped_json,
        }
        video_stmt = sa.select(ssco_model.Video).where(ssco_model.Video.youtube_vid == video_id)
        assert (video_record := ssco_crud.videoCRUD.get_using_query(session, video_stmt))  # nosec B101
        video_record = ssco_crud.videoCRUD.update(
            session,
            db_obj=video_record,
            obj_in=ssco_schema.VideoUpdate(**video_obj_kwargs),
        )

        for file_record in file_records.values():
            video_record.files.add(file_record)

        session.commit()
