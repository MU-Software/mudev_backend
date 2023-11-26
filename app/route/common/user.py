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


@router.get(path="/csrf/")
async def set_csrf_token(
    response: fastapi.Response,
    setting: common_dep.settingDI,
    csrf_token: header_dep.csrf_token = None,
    force: bool = False,
) -> fastapi.responses.JSONResponse:
    if not csrf_token or force:
        cookie_util.Cookie.model_validate(
            {
                **setting.to_cookie_config(),
                **cookie_const.CookieKey.CSRF_TOKEN.to_cookie_config(),
                "value": str(uuid.uuid4()),
            }
        ).set_cookie(response)

    response.status_code = 204
    return response


@router.post(path="/signup/", response_model=user_schema.UserDTO)
async def signup(db_session: common_dep.dbDI, payload: user_schema.UserCreate) -> user_model.User:
    return await user_crud.userCRUD.create(db_session, obj_in=payload)


@router.post(path="/signin/", response_model=user_schema.UserSignInDTO)
async def signin(
    response: fastapi.responses.Response,
    setting: common_dep.settingDI,
    db_session: common_dep.dbDI,
    redis_session: common_dep.redisDI,
    payload: user_schema.UserSignIn,
    user_ip: header_dep.user_ip = None,
    user_agent: header_dep.user_agent = None,
    csrf_token: header_dep.csrf_token = None,
) -> dict:
    user = await user_crud.userCRUD.signin(db_session, obj_in=payload)
    await db_session.refresh(user)  # TODO: Remove this

    refresh_token_obj = await user_crud.userSignInHistoryCRUD.claim_refresh_token(
        session=db_session,
        redis_session=redis_session,
        db_obj=await user_crud.userSignInHistoryCRUD.create(
            session=db_session,
            obj_in=user_schema.UserSignInHistoryCreate(user_uuid=user.uuid, ip=user_ip, user_agent=user_agent),
        ),
        config_obj=setting,
        request_user_agent=user_agent,
    )
    refresh_token_obj.set_cookie(config_obj=setting, response=response)
    response.status_code = 201

    return {
        "user": user,
        "token": {
            "refresh_token": refresh_token_obj,
            "access_token": refresh_token_obj.to_access_token(csrf_token=csrf_token),
        },
    }


@router.delete(path="/signout/")
async def signout(
    setting: common_dep.settingDI,
    db_session: common_dep.dbDI,
    redis_session: common_dep.redisDI,
    access_token: authn_dep.optional_access_token_di = None,
) -> fastapi.responses.Response:
    response = fastapi.responses.Response(status_code=204)

    if access_token:
        for cookie_key in (cookie_const.CookieKey.REFRESH_TOKEN, cookie_const.CookieKey.CSRF_TOKEN):
            kwargs = {**setting.to_cookie_config(), **cookie_key.to_cookie_config()}
            cookie_util.Cookie.model_validate(kwargs).delete_cookie(response)
        await user_crud.userSignInHistoryCRUD.revoke(
            session=db_session,
            redis_session=redis_session,
            uuid=access_token.token_obj.jti,
            user_uuid=access_token.token_obj.user,
        )

    return response


@router.get(path="/refresh/", response_model=user_schema.UserJWTDTO)
async def refresh(
    setting: common_dep.settingDI,
    db_session: common_dep.dbDI,
    redis_session: common_dep.redisDI,
    user_agent: header_dep.user_agent,
    csrf_token: header_dep.csrf_token,
    refresh_token: authn_dep.refresh_token_di,
) -> dict[str, user_schema.RefreshToken | user_schema.AccessToken]:
    signin_history = await user_crud.userSignInHistoryCRUD.get(db_session, refresh_token.token_obj.jti)
    refresh_token_obj = await user_crud.userSignInHistoryCRUD.claim_refresh_token(
        session=db_session,
        redis_session=redis_session,
        db_obj=signin_history,
        config_obj=setting,
        request_user_agent=user_agent,
    )

    return {
        "refresh_token": refresh_token_obj,
        "access_token": refresh_token_obj.to_access_token(csrf_token=csrf_token),
    }


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
    access_token: authn_dep.access_token_di,
    payload: user_schema.UserUpdate,
) -> user_model.User:
    user = await user_crud.userCRUD.get(db_session, access_token.token_obj.user)
    return await user_crud.userCRUD.update(db_session, db_obj=user, obj_in=payload)


@router.get(path="/{username}/", response_model=user_schema.UserDTO)
async def get_user(db_session: common_dep.dbDI, username: str) -> user_model.User:
    return await user_crud.userCRUD.get_using_query(
        db_session,
        sa.select(user_model.User).where(user_model.User.username == username),
    )


history_router = fastapi.APIRouter(tags=[tag_const.OpenAPITag.USER_HISTORY], prefix="/signin-history")
router.include_router(history_router)


@history_router.get(path="/", response_model=list[user_schema.UserSignInHistoryDTO])
async def get_signin_history(
    db_session: common_dep.dbDI,
    access_token: authn_dep.access_token_di,
) -> typing.Iterable[user_model.UserSignInHistory]:
    stmt = sa.select(user_model.UserSignInHistory).where(
        user_model.UserSignInHistory.user_uuid == access_token.token_obj.user
    )
    return await user_crud.userSignInHistoryCRUD.get_multi_using_query(db_session, stmt)


@history_router.delete(path="/{usih_uuid}")
async def revoke_signin_history(
    db_session: common_dep.dbDI,
    redis_session: common_dep.redisDI,
    access_token: authn_dep.access_token_di,
    usih_uuid: str,
) -> fastapi.responses.JSONResponse:
    await user_crud.userSignInHistoryCRUD.revoke(
        session=db_session,
        redis_session=redis_session,
        uuid=usih_uuid,
        user_uuid=access_token.token_obj.user,
    )
    return fastapi.responses.JSONResponse(status_code=204)
