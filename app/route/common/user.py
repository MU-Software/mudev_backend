from __future__ import annotations

import typing
import uuid

import fastapi
import fastapi.responses
import fastapi.security
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
import app.util.mu_string as mu_string

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


@router.post(path="/signin/", response_model=user_schema.UserTokenResponse)
async def signin(
    db_session: common_dep.dbDI,
    config_obj: common_dep.settingDI,
    user_ip: header_dep.user_ip,
    user_agent: header_dep.user_agent,
    csrf_token: header_dep.csrf_token,
    form_data: typing.Annotated[fastapi.security.OAuth2PasswordRequestForm, fastapi.Depends()],
    response: fastapi.Response,
) -> dict:
    if form_data.username.startswith("@"):
        column, username = user_model.User.username, form_data.username[1:]
    elif "@" in form_data.username and mu_string.is_email(form_data.username):
        column, username = user_model.User.email, form_data.username
    column, username = user_model.User.username, form_data.username

    user = await user_crud.userCRUD.signin(db_session, column=column, user_ident=username, password=form_data.password)
    await db_session.refresh(user)  # TODO: Remove this

    refresh_token_obj = await user_crud.userSignInHistoryCRUD.signin(
        session=db_session,
        obj_in=user_schema.UserSignInHistoryCreate(
            user_uuid=user.uuid,
            ip=user_ip,
            user_agent=user_agent,
            config_obj=config_obj,
        ),
    )
    refresh_token_obj.set_cookie(response)
    response.status_code = 201
    return {"access_token": refresh_token_obj.to_access_token(csrf_token=csrf_token).jwt}


@router.delete(path="/signout/")
async def signout(
    db_session: common_dep.dbDI,
    redis_session: common_dep.redisDI,
    config_obj: common_dep.settingDI,
    access_token: authn_dep.access_token_di,
    response: fastapi.Response,
) -> fastapi.responses.Response:
    for cookie_key in (cookie_const.CookieKey.REFRESH_TOKEN, cookie_const.CookieKey.CSRF_TOKEN):
        kwargs = {**config_obj.to_cookie_config(), **cookie_key.to_cookie_config()}
        cookie_util.Cookie.model_validate(kwargs).delete_cookie(response)

    await user_crud.userSignInHistoryCRUD.revoke(
        session=db_session,
        redis_session=redis_session,
        token_obj=access_token,
    )

    response.status_code = 204
    return response


@router.get(path="/refresh/", response_model=user_schema.UserTokenResponse)
async def refresh(
    db_session: common_dep.dbDI,
    csrf_token: header_dep.csrf_token,
    refresh_token: authn_dep.refresh_token_di,
    response: fastapi.Response,
) -> dict:
    refresh_token = await user_crud.userSignInHistoryCRUD.refresh(session=db_session, token_obj=refresh_token)
    refresh_token.set_cookie(response)
    return {"access_token": refresh_token.to_access_token(csrf_token=csrf_token).jwt, "token_type": "bearer"}


@router.post(path="/update-password/", response_model=user_schema.UserDTO)
async def update_password(
    db_session: common_dep.dbDI,
    access_token: authn_dep.access_token_di,
    payload: user_schema.UserPasswordUpdate,
) -> user_model.User:
    return await user_crud.userCRUD.update_password(
        session=db_session,
        uuid=access_token.user,
        obj_in=payload,
    )


# TODO: Implement this
# @router.post(path="/reset-password/")
# async def reset_password(
#     db_session: common_dep.dbDI,
#     payload: user_schema.UserPasswordReset,
# ) -> None:
#     return await user_crud.userCRUD.reset_password(db_session, payload)


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
async def get_user(db_session: common_dep.dbDI, username: str) -> user_model.User:
    stmt = sa.select(user_model.User).where(user_model.User.username == username)
    return await user_crud.userCRUD.get_using_query(db_session, stmt)


@router.get(path="/signin-history/", response_model=list[user_schema.UserSignInHistoryDTO])
async def get_signin_history(
    db_session: common_dep.dbDI, access_token: authn_dep.access_token_di
) -> typing.Iterable[user_model.UserSignInHistory]:
    stmt = sa.select(user_model.UserSignInHistory).where(user_model.UserSignInHistory.user_uuid == access_token.user)
    return await user_crud.userSignInHistoryCRUD.get_multi_using_query(db_session, stmt)


@router.delete(path="/signin-history/{usih_uuid}")
async def revoke_signin_history(
    db_session: common_dep.dbDI,
    redis_session: common_dep.redisDI,
    access_token: authn_dep.access_token_di,
    usih_uuid: str,
    response: fastapi.Response,
) -> None:
    # TODO: 403 응답을 문서화하기
    if str(access_token.jti) == usih_uuid:
        error_msg = "현재 로그인 중인 기기를 로그아웃하시려면, 로그아웃 기능을 사용해주세요."
        raise fastapi.HTTPException(status_code=403, detail=error_msg)

    await user_crud.userSignInHistoryCRUD.revoke(
        session=db_session,
        redis_session=redis_session,
        token_obj=access_token,
    )
    response.status_code = 204
