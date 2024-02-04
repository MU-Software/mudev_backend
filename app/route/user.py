from __future__ import annotations

import fastapi
import fastapi.responses
import fastapi.security
import sqlalchemy as sa

import app.const.error as error_const
import app.const.tag as tag_const
import app.crud.user as user_crud
import app.db.model.user as user_model
import app.dependency.authn as authn_dep
import app.dependency.common as common_dep
import app.schema.user as user_schema

router = fastapi.APIRouter(tags=[tag_const.OpenAPITag.USER], prefix="/user")


@router.get(path="/info/me/", response_model=user_schema.UserDTO)
async def get_me(db_session: common_dep.dbDI, access_token: authn_dep.access_token_di) -> user_model.User:
    return await user_crud.userCRUD.get(db_session, access_token.user)


@router.post(path="/info/me/", response_model=user_schema.UserDTO)
async def update_me(
    db_session: common_dep.dbDI,
    access_token: authn_dep.access_token_di,
    payload: user_schema.UserUpdate,
) -> user_model.User:
    user = await user_crud.userCRUD.get(db_session, access_token.user)
    return await user_crud.userCRUD.update(db_session, db_obj=user, obj_in=payload)


@router.get(path="/info/{username}/", response_model=user_schema.UserDTO)
async def get_user(
    db_session: common_dep.dbDI,
    username: str,
    access_token: authn_dep.access_token_or_none_di,
) -> user_model.User:
    stmt = sa.select(user_model.User).where(user_model.User.username == username)
    if not (result := await user_crud.userCRUD.get_using_query(db_session, stmt)):
        error_const.ClientError.RESOURCE_NOT_FOUND().raise_()
    if result.private and (not access_token or result.uuid != access_token.user):
        error_const.AuthZError.PERMISSION_DENIED().raise_()
    return result
