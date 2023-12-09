import typing
import uuid

import fastapi
import pydantic
import sqlalchemy as sa

import app.const.tag as tag_const
import app.crud.file as file_crud
import app.db.model.file as file_model
import app.dependency.authn as authn_dep
import app.dependency.common as common_dep
import app.schema.file as file_schema
import app.schema.user as user_schema
import app.util.mu_file as mu_file
import app.util.time_util as time_util

router = fastapi.APIRouter(tags=[tag_const.OpenAPITag.USER_FILE], prefix="/file")


def check_file_permission(file: file_model.File | None, token_obj: user_schema.AccessToken | None) -> file_model.File:
    if not file or file.deleted_at:
        raise fastapi.HTTPException(status_code=404, detail="File not found")
    if file.private and (not token_obj or file.created_by_uuid != token_obj.user):
        raise fastapi.HTTPException(status_code=403, detail="File is private")
    return file


@router.get(path="/", response_model=list[file_schema.FileInfoDTO])
async def list_user_file_infos(
    db_session: common_dep.dbDI, access_token: authn_dep.access_token_di
) -> typing.Iterable[file_model.File]:
    """유저의 파일 목록을 반환합니다."""
    stmt = sa.select(file_model.File).where(file_model.File.created_by_uuid == access_token.user)
    return await file_crud.fileCRUD.get_multi_using_query(db_session, stmt)


@router.get(path="/{file_id}/info/", response_model=file_schema.FileInfoDTO)
async def get_file_info(
    file_id: str | uuid.UUID,
    db_session: common_dep.dbDI,
    access_token: authn_dep.access_token_or_none_di,
) -> file_model.File:
    """파일 정보를 반환합니다."""
    return check_file_permission(await file_crud.fileCRUD.get(db_session, file_id), access_token)


@router.head(path="/{file_id}/")
async def get_file_metadata(
    file_id: str | uuid.UUID,
    db_session: common_dep.dbDI,
    access_token: authn_dep.access_token_or_none_di,
) -> fastapi.responses.Response:
    """파일 메타데이터를 반환합니다."""
    file_record = check_file_permission(await file_crud.fileCRUD.get(db_session, file_id), access_token)
    file_metadata = file_schema.FileMetadataDTO.model_validate(file_record)
    return fastapi.Response(headers=file_metadata.model_dump_as_head_header())


@router.get(path="/{file_id}/")
async def get_file_binary(
    file_id: str | uuid.UUID,
    db_session: common_dep.dbDI,
    access_token: authn_dep.access_token_or_none_di,
) -> fastapi.responses.FileResponse:
    """파일의 미리보기를 제공합니다."""
    file_record = check_file_permission(await file_crud.fileCRUD.get(db_session, file_id), access_token)
    file_metadata = file_schema.FileMetadataDTO.model_validate(file_record)
    return fastapi.responses.FileResponse(
        path=file_record.path,
        headers=file_metadata.model_dump_as_preview_header(),
        media_type=file_record.mimetype,
    )


@router.get(path="/{file_id}/download/")
async def download_file_binary(
    file_id: str | uuid.UUID,
    db_session: common_dep.dbDI,
    access_token: authn_dep.access_token_or_none_di,
) -> fastapi.responses.FileResponse:
    """파일을 다운로드합니다."""
    file_record = check_file_permission(await file_crud.fileCRUD.get(db_session, file_id), access_token)
    file_metadata = file_schema.FileMetadataDTO.model_validate(file_record)
    return fastapi.responses.FileResponse(
        path=file_record.path,
        headers=file_metadata.model_dump_as_download_header(),
        media_type=file_record.mimetype,
    )


@router.post(path="/", response_model=file_schema.FileInfoDTO)
async def upload_file(
    config_obj: common_dep.settingDI,
    db_session: common_dep.dbDI,
    access_token: authn_dep.access_token_di,
    # TODO: FIXME: There must be a better way to do this using pydantic
    uploadfile: fastapi.UploadFile,
    data: typing.Annotated[pydantic.Json | None, fastapi.Form()] = None,
    private: typing.Annotated[bool, fastapi.Form()] = False,
    readable: typing.Annotated[bool, fastapi.Form()] = True,
    writable: typing.Annotated[bool, fastapi.Form()] = False,
) -> file_model.File:
    """파일을 업로드합니다."""
    current_timestamp: int = int(time_util.get_utcnow().timestamp())
    save_path = config_obj.upload_dir / f"{access_token.user}" / f"{current_timestamp}_{uploadfile.filename}"
    await mu_file.async_save_tempfile(save_path=save_path, fp=uploadfile.file)

    new_file_info = file_schema.FileCreate(
        path=save_path,
        data=data,
        private=private,
        readable=readable,
        writable=writable,
        config_obj=config_obj,
        created_by_uuid=access_token.user,
    )
    return await file_crud.fileCRUD.create(db_session, obj_in=new_file_info)
