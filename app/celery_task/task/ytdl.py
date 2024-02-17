import asyncio
import json
import logging
import pathlib as pt
import time
import typing
import uuid

import celery
import ffmpeg
import sqlalchemy as sa
import telegram

import app.celery_task.__interface__ as celery_interface
import app.const.celery as celery_const
import app.const.sns as sns_const
import app.crud.file as file_crud
import app.crud.ssco as ssco_crud
import app.crud.user as user_crud
import app.db.model.file as file_model
import app.db.model.ssco as ssco_model
import app.db.model.task as task_model
import app.schema.file as file_schema
import app.schema.ssco as ssco_schema
import app.util.ext_api.docker as docker_util
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


def run_ffmpeg_for_video_to_m4a_and_mp3(video_path: pt.Path, coverart_path: pt.Path) -> dict[str, pt.Path]:
    """ffmpeg를 이용해 영상 파일을 m4a와 mp3 파일로 변환하는 명령어를 생성합니다."""
    target_video_path = video_path
    target_coverart_path = coverart_path
    if docker_util.is_container():
        target_video_path = docker_util.resolve_container_path_to_host(video_path)
        target_coverart_path = docker_util.resolve_container_path_to_host(coverart_path)
    target_mp3_path = target_video_path.with_suffix(".mp3")
    target_m4a_path = target_video_path.with_suffix(".m4a")

    original_file_node = ffmpeg.input(target_video_path.as_posix())
    audio_node = original_file_node.audio.filter("silenceremove", "1", "0", "-50dB").filter_multi_output("asplit")
    m4a_output_node = audio_node.stream(1).output(target_m4a_path.as_posix())
    mp3_output_node = (
        audio_node.stream(0)
        .output(ffmpeg.input(target_coverart_path), target_mp3_path.as_posix())
        .global_args("-disposition:0", "attached_pic")
        .global_args("-id3v2_version", "3")
    )
    merged_node: ffmpeg.nodes.Node = ffmpeg.merge_outputs(mp3_output_node, m4a_output_node)

    if docker_util.is_container():
        compiled_args: list[str] = ffmpeg.compile(merged_node, overwrite_output=True)
        stdout, stderr = docker_util.run_cmd_on_host(compiled_args)
        logger.debug(f"ffmpeg stdout:\n{stdout}")
        logger.debug(f"ffmpeg stderr:\n{stderr}")
    else:
        ffmpeg_run: tuple[str, str] = ffmpeg.run(merged_node, overwrite_output=True, quiet=True)
        stdout, stderr = ffmpeg_run
        logger.debug(f"ffmpeg stdout:\n{stdout}")
        logger.debug(f"ffmpeg stderr:\n{stderr}")

    return {ext: video_path.with_suffix(f".{ext}") for ext in ["mp3", "m4a"]}


@celery.shared_task(bind=True, base=celery_interface.SessionTask)
def ytdl_downloader_task(self: celery_interface.SessionTask[None], *, youtube_vid: str) -> None:
    """youtube-dl을 이용해 비디오를 다운로드하고, Video와 File row를 생성합니다."""
    raise_if_task_not_runnable(self)

    save_dir = self.config_obj.project.upload_to.youtube_video_dir(youtube_vid)
    download_info = youtube_util.download_video(youtube_vid, save_dir)

    file_paths: dict[str, pt.Path] = {}
    file_paths["video"] = download_info.file_path
    file_paths["thumbnail"] = youtube_util.download_thumbnail(youtube_vid, save_dir)

    audio_paths = run_ffmpeg_for_video_to_m4a_and_mp3(file_paths["video"], file_paths["thumbnail"])
    file_paths |= audio_paths
    file_download_urls: dict[str, str] = {}

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
            "data": json.dumps(download_info.data),
        }
        video_stmt = sa.select(ssco_model.Video).where(ssco_model.Video.youtube_vid == youtube_vid)
        assert (video_record := ssco_crud.videoCRUD.get_using_query(session, video_stmt))  # nosec B101
        video_record = ssco_crud.videoCRUD.update(
            session,
            db_obj=video_record,
            obj_in=ssco_schema.VideoUpdate(**video_obj_kwargs),
        )

        for file_record in file_records.values():
            video_record.files.add(file_record)

        session.commit()

        for row in file_records.values():
            session.refresh(row)
            ext = typing.cast(pt.Path, row.path).suffix.replace(".", "")
            file_download_urls[ext] = f"{self.config_obj.project.backend_domain}/file/{row.uuid}/download/"

    # 완료 후, 요청한 유저에게 알림을 보냅니다.
    # route에서 등록하는 중에 알림을 보내는 일을 방지하기 위해, 3초 후에 알림을 보내도록 합니다.
    time.sleep(3)

    telegram_bot_token = self.config_obj.project.ssco.telegram_bot_token.get_secret_value()
    telegram_bot = telegram.Bot(token=telegram_bot_token)
    telegram_button = telegram.InlineKeyboardMarkup(
        [
            [telegram.InlineKeyboardButton(text=f"{ext.upper()} 파일 다운로드", url=url)]
            for ext, url in file_download_urls.items()
        ]
    )

    chat_ids: set[int] = set()
    with self.sync_db.get_sync_session() as session:
        video_record = ssco_crud.videoCRUD.get_using_query(session, video_stmt)
        for user in video_record.users:
            # TODO: 아직은 유저가 텔레그램 연동을 해야만 알림을 보낼 수 있습니다.
            target_sns = sns_const.SNSAuthInfoUserAgentEnum.telegram
            clients = user_crud.snsAuthInfoCRUD.get_user_sns_tokens(session, user.uuid, target_sns)
            chat_ids |= {c.chat_id for c in clients if c.chat_id}

    message_tasks = [
        telegram_bot.send_message(
            chat_id=c,
            text=f"영상이 준비됐어요!\n{video_record.title}",
            reply_markup=telegram_button,
        )
        for c in chat_ids
    ]
    asyncio.get_event_loop().run_until_complete(asyncio.gather(*message_tasks))
