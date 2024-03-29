import typing

import fastapi
import sqlalchemy as sa
import sqlalchemy.orm as sa_orm

import app.celery_task.task.ytdl as ytdl_task
import app.const.tag as tag_const
import app.crud.ssco as ssco_crud
import app.crud.user as user_crud
import app.db.model.ssco as ssco_model
import app.dependency.authn as authn_dep
import app.dependency.common as common_dep
import app.schema.ssco as ssco_schema

router = fastapi.APIRouter(tags=[tag_const.OpenAPITag.YTDL], prefix="/ssco/ytdl")


@router.get(path="/", response_model=list[ssco_schema.VideoDTO])
async def get_user_videos(
    db_session: common_dep.dbDI,
    access_token: authn_dep.access_token_di,
) -> typing.Iterable[ssco_model.Video]:
    """유저의 비디오 목록을 반환합니다."""
    stmt = (
        sa.select(ssco_model.Video)
        .join(ssco_model.VideoUserRelation)
        .where(ssco_model.VideoUserRelation.user_uuid == access_token.user)
        .options(sa_orm.joinedload(ssco_model.Video.files))
    )
    return (await ssco_crud.videoCRUD.get_multi_using_query(db_session, stmt)).unique().all()


@router.post(path="/")
async def create_video_download_task(
    db_session: common_dep.dbDI,
    access_token: authn_dep.access_token_di,
    payload: ssco_schema.VideoDownloadRequestPayload,
) -> None:
    """비디오 다운로드 작업을 생성합니다."""
    stmt = sa.select(ssco_model.Video).where(ssco_model.Video.youtube_vid == payload.youtube_vid)
    if not (video_record := await ssco_crud.videoCRUD.get_using_query(db_session, stmt)):
        video_create_obj = ssco_schema.VideoCreate(youtube_vid=payload.youtube_vid)
        video_record = await ssco_crud.videoCRUD.create(db_session, obj_in=video_create_obj)
        ytdl_task.ytdl_downloader_task.delay(youtube_vid=payload.youtube_vid)

    await db_session.refresh(video_record, attribute_names=["users"])
    video_record.users.add(await user_crud.userCRUD.get(db_session, uuid=access_token.user))
    await db_session.commit()
