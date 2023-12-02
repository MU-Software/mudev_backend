from __future__ import annotations

import typing
import uuid

import fastapi
import fastapi.responses
import sqlalchemy as sa

import app.const.cookie as cookie_const
import app.const.tag as tag_const
import app.crud.user as user_crud
import app.db.model.user as user_model
import app.dependency.authn as authn_dep
import app.dependency.common as common_dep
import app.dependency.header as header_dep
import app.schema.user as user_schema
import app.util.fastapi.cookie as cookie_util

router = fastapi.APIRouter(tags=[tag_const.OpenAPITag.USER], prefix="/user")


@router.head(path="/csrf/")
async def set_csrf_token(
    response: fastapi.Response,
    setting: common_dep.settingDI,
    csrf_token: header_dep.csrf_token = None,
    force: bool = False,
) -> fastapi.responses.JSONResponse:
    if not csrf_token or force:
        cookie_util.Cookie(
            **setting.to_cookie_config(),
            **cookie_const.CookieKey.CSRF_TOKEN.to_cookie_config(),
            value=str(uuid.uuid4()),
        ).set_cookie(response)

    response.status_code = 204
    return response


@router.post(path="/signup/", response_model=user_schema.UserDTO)
async def signup(db_session: common_dep.dbDI, payload: user_schema.UserCreate) -> user_model.User:
    return await user_crud.userCRUD.create(db_session, obj_in=payload)


@router.post(path="/signin/", response_model=user_schema.UserSignInDTO)
async def signin(
    db_session: common_dep.dbDI,
    config_obj: common_dep.settingDI,
    user_ip: header_dep.user_ip,
    user_agent: header_dep.user_agent,
    csrf_token: header_dep.csrf_token,
    payload: user_schema.UserSignIn,
    response: fastapi.Response,
) -> dict:
    user = await user_crud.userCRUD.signin(db_session, obj_in=payload)
    await db_session.refresh(user)  # TODO: Remove this

    signin_history_create_payload = user_schema.UserSignInHistoryCreate(
        user_uuid=user.uuid,
        ip=user_ip,
        user_agent=user_agent,
        config_obj=config_obj,
    )
    refresh_token_obj = await user_crud.userSignInHistoryCRUD.signin(
        session=db_session, obj_in=signin_history_create_payload
    )

    response.status_code = 201
    return {"user": user, "token": refresh_token_obj.get_response(response, config_obj)}


@router.delete(path="/signout/")
async def signout(
    db_session: common_dep.dbDI,
    redis_session: common_dep.redisDI,
    config_obj: common_dep.settingDI,
    access_token_di: authn_dep.access_token_di,
    response: fastapi.Response,
) -> fastapi.responses.Response:
    for cookie_key in (cookie_const.CookieKey.REFRESH_TOKEN, cookie_const.CookieKey.CSRF_TOKEN):
        kwargs = {**config_obj.to_cookie_config(), **cookie_key.to_cookie_config()}
        cookie_util.Cookie.model_validate(kwargs).delete_cookie(response)

    await user_crud.userSignInHistoryCRUD.revoke(
        session=db_session,
        redis_session=redis_session,
        token_obj=access_token_di.token_obj,
    )

    response.status_code = 204
    return response


@router.get(path="/refresh/", response_model=user_schema.UserJWTDTO)
async def refresh(db_session: common_dep.dbDI, refresh_token: authn_dep.refresh_token_di) -> dict:
    token_obj = await user_crud.userSignInHistoryCRUD.refresh(session=db_session, token_obj=refresh_token.token_obj)
    return token_obj.get_response(refresh_token.response, refresh_token.config_obj)


@router.post(path="/update-password/", response_model=user_schema.UserDTO)
async def update_password(
    db_session: common_dep.dbDI,
    access_token: authn_dep.access_token_di,
    payload: user_schema.UserPasswordUpdate,
) -> user_model.User:
    return await user_crud.userCRUD.update_password(
        session=db_session,
        uuid=access_token.token_obj.user,
        obj_in=payload,
    )


# TODO: Implement this
# @router.post(path="/reset-password/")
# async def reset_password(
#     db_session: common_dep.dbDI,
#     payload: user_schema.UserPasswordReset,
# ) -> None:
#     return await user_crud.userCRUD.reset_password(db_session, payload)


@router.get(path="/me/", response_model=user_schema.UserDTO)
async def get_me(db_session: common_dep.dbDI, access_token: authn_dep.access_token_di) -> user_model.User:
    return user_crud.userCRUD.get(db_session, access_token.token_obj.user)


@router.post(path="/me/", response_model=user_schema.UserDTO)
async def update_me(
    db_session: common_dep.dbDI,
    access_token_di: authn_dep.access_token_di,
    payload: user_schema.UserUpdate,
) -> user_model.User:
    user = await user_crud.userCRUD.get(db_session, access_token_di.token_obj.user)
    return await user_crud.userCRUD.update(db_session, db_obj=user, obj_in=payload)


@router.get(path="/{username}/", response_model=user_schema.UserDTO)
async def get_user(db_session: common_dep.dbDI, username: str) -> user_model.User:
    stmt = sa.select(user_model.User).where(user_model.User.username == username)
    return await user_crud.userCRUD.get_using_query(db_session, stmt)


history_router = fastapi.APIRouter(tags=[tag_const.OpenAPITag.USER_HISTORY], prefix="/signin-history")
router.include_router(history_router)


@history_router.get(path="/", response_model=list[user_schema.UserSignInHistoryDTO])
async def get_signin_history(
    db_session: common_dep.dbDI,
    access_token_di: authn_dep.access_token_di,
) -> typing.Iterable[user_model.UserSignInHistory]:
    user_uuid = access_token_di.token_obj.user
    stmt = sa.select(user_model.UserSignInHistory).where(user_model.UserSignInHistory.user_uuid == user_uuid)
    return await user_crud.userSignInHistoryCRUD.get_multi_using_query(db_session, stmt)


@history_router.delete(path="/{usih_uuid}")
async def revoke_signin_history(
    db_session: common_dep.dbDI,
    redis_session: common_dep.redisDI,
    access_token_di: authn_dep.access_token_di,
    usih_uuid: str,
) -> fastapi.responses.JSONResponse:
    token_obj = access_token_di.token_obj

    # TODO: 403 응답을 문서화하기
    if token_obj.jti == usih_uuid:
        error_msg = "현재 로그인 중인 기기를 로그아웃하시려면, 로그아웃 기능을 사용해주세요."
        raise fastapi.HTTPException(status_code=403, detail=error_msg)

    await user_crud.userSignInHistoryCRUD.revoke(session=db_session, redis_session=redis_session, token_obj=token_obj)
    return fastapi.responses.JSONResponse(status_code=204)
