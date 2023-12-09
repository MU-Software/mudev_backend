import asyncio
import pathlib as pt
import sys
import tempfile
import typing
import uuid

import celery
import ffmpeg
import sqlalchemy as sa

import app.celery_task.__interface__ as celery_interface
import app.const.celery as celery_const
import app.crud.file as file_crud
import app.crud.ssco as ssco_crud
import app.db.model.ssco as ssco_model
import app.db.model.task as task_model
import app.schema.file as file_schema
import app.schema.ssco as ssco_schema
import app.util.ext_api.youtube as youtube_util


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
    if not task.task_instance.startable:
        raise task.retry(**retry_kwargs, exc=RuntimeError("Task is not startable"))

    import app.celery_task.task.ytdl_updater as ytdl_updater

    ytdl_updater_task_name: str = ytdl_updater.ytdl_updater_task.name
    stmt = sa.select(sa.exists(task_model.Task)).where(
        task_model.Task.celery_task_name == ytdl_updater_task_name,
        task_model.Task.startable.is_(True),
        task_model.Task.state != celery_const.CeleryTaskStatus.SUCCESS,
    )
    with task.db_session as session:
        if bool(session.execute(stmt).scalar_one_or_none()):
            task.task_instance.startable = False
            session.commit()
            raise task.retry(**retry_kwargs, exc=RuntimeError("Updater is running"))


async def get_cover_art_file(youtube_vid: str) -> typing.IO[bytes]:
    tmp_file = tempfile.NamedTemporaryFile(delete=True)
    tmp_file_path = pt.Path(tmp_file.name)
    await youtube_util.download_thumbnail_img_by_video_id(video_id=youtube_vid, save_path=tmp_file_path)
    return tmp_file


async def download_video(
    youtube_vid: str, target_path: pt.Path, force_overwrite: bool = True
) -> youtube_util.YoutubeDLPResult:
    video_download_info = await youtube_util.downalod_video_from_video_id(
        executable_info=["poetry", "run", sys.executable, "-m", "yt_dlp"],
        video_id=youtube_vid,
        target_path=target_path,
        force_overwrite=force_overwrite,
    )

    # ffmpeg를 이용해 영상 파일을 m4a와 mp3 파일로 변환
    cover_art_file: typing.IO[bytes] = await get_cover_art_file(youtube_vid)
    cover_art_path = pt.Path(cover_art_file.name)
    video_path = video_download_info.file_path
    mp3_path = video_path.with_suffix(".mp3")
    m4a_path = video_path.with_suffix(".m4a")

    ffmpeg_audio_node = (
        ffmpeg.input(video_path).audio.filter("silenceremove", "1", "0", "-50dB").filter_multi_output("asplit")
    )
    ffmpeg_m4a_output_node = ffmpeg_audio_node.stream(1).output(m4a_path.as_posix())
    ffmpeg_mp3_output_node = (
        ffmpeg_audio_node.stream(0)
        .output(ffmpeg.input(cover_art_path), mp3_path.as_posix())
        .global_args("-disposition:0", "attached_pic")
        .global_args("-id3v2_version", "3")
    )
    ffmpeg.merge_outputs(ffmpeg_mp3_output_node, ffmpeg_m4a_output_node).run(overwrite_output=True)

    return video_download_info


@celery.shared_task(bind=True, base=celery_interface.SessionTask)
def ytdl_downloader_task(
    self: celery_interface.SessionTask[None],
    *,
    youtube_vid: str,
    target_path_str: str,
    user_uuid: uuid.UUID,
    force_overwrite: bool = True,
) -> None:
    target_path: pt.Path = pt.Path(target_path_str)
    raise_if_task_not_runnable(self)

    event_loop = asyncio.get_event_loop()
    if not (video_record := ssco_crud.videoCRUD.get_by_youtube_vid(self.db_session, youtube_vid=youtube_vid)):
        video_info_coro = download_video(youtube_vid, target_path, force_overwrite)
        video_info = event_loop.run_until_complete(video_info_coro)
        video_path = video_info.file_path
        video_create_obj = ssco_schema.VideoCreate(
            youtube_vid=youtube_vid,
            title=video_info.title,
            data=video_info.dumped_json,
        )
        video_record = ssco_crud.videoCRUD.create(self.db_session, obj_in=video_create_obj)

        for filepath in (video_path, video_path.with_suffix(".mp3"), video_path.with_suffix(".m4a")):
            with self.db_session as session:
                file_obj = file_schema.FileCreate(path=filepath, created_by_uuid=user_uuid)
                file_record = file_crud.fileCRUD.create(session, obj_in=file_obj)
                ssco_crud.videoCRUD.add_file(session, video_record.uuid, file_record.uuid)

    with self.db_session as session:
        session.add(ssco_model.VideoUserRelation(video_uuid=video_record.uuid, user_uuid=user_uuid))
        session.commit()
