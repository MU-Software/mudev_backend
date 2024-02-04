from __future__ import annotations

import typing
import uuid

import fastapi
import fastapi.responses
import fastapi.security
import sqlalchemy as sa

import app.const.cookie as cookie_const
import app.const.error as error_const
import app.const.tag as tag_const
import app.crud.user as user_crud
import app.db.model.user as user_model
import app.dependency.authn as authn_dep
import app.dependency.common as common_dep
import app.dependency.header as header_dep
import app.schema.user as user_schema
import app.util.fastapi as fastapi_util
import app.util.fastapi.cookie as cookie_util

router = fastapi.APIRouter(tags=[tag_const.OpenAPITag.AUTHN], prefix="/authn")


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
    payload: typing.Annotated[fastapi.security.OAuth2PasswordRequestForm, fastapi.Depends()],
    response: fastapi.Response,
) -> dict:
    user = await user_crud.userCRUD.signin(db_session, user_ident=payload.username, password=payload.password)
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

    await user_crud.userSignInHistoryCRUD.delete(
        session=db_session,
        redis_session=redis_session,
        token=access_token,
    )

    response.status_code = 204
    return response


@router.put(path="/verify/", response_model=fastapi_util.EmptyResponseSchema)
async def verify(access_token: authn_dep.access_token_di) -> dict:
    return {"message": "ok"}


@router.get(path="/refresh/", response_model=user_schema.UserTokenResponse)
async def refresh(
    db_session: common_dep.dbDI,
    csrf_token: header_dep.csrf_token,
    refresh_token: authn_dep.refresh_token_di,
    response: fastapi.Response,
) -> dict:
    refresh_token = await user_crud.userSignInHistoryCRUD.refresh(session=db_session, token=refresh_token)
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


@router.get(
    path="/signin-history/",
    response_model=list[user_schema.UserSignInHistoryDTO],
    tags=[tag_const.OpenAPITag.USER_SIGNIN_HISTORY],
)
async def get_signin_history(
    db_session: common_dep.dbDI, access_token: authn_dep.access_token_di
) -> typing.Iterable[user_model.UserSignInHistory]:
    stmt = sa.select(user_model.UserSignInHistory).where(user_model.UserSignInHistory.user_uuid == access_token.user)
    return await user_crud.userSignInHistoryCRUD.get_multi_using_query(db_session, stmt)


@router.delete(path="/signin-history/{usih_uuid}", tags=[tag_const.OpenAPITag.USER_SIGNIN_HISTORY])
async def revoke_signin_history(
    db_session: common_dep.dbDI,
    redis_session: common_dep.redisDI,
    access_token: authn_dep.access_token_di,
    usih_uuid: uuid.UUID,
    response: fastapi.Response,
) -> None:
    if access_token.jti == usih_uuid:
        error_const.AuthNError.SELF_REVOKE_NOT_ALLOWED().raise_()

    await user_crud.userSignInHistoryCRUD.delete(
        session=db_session,
        redis_session=redis_session,
        token=access_token,
    )
    response.status_code = 204


@router.post(path="/sns/", response_model=fastapi_util.EmptyResponseSchema)
async def register_sns_auth(
    db_session: common_dep.dbDI,
    config_obj: common_dep.settingDI,
    user_ip: header_dep.user_ip,
    access_token: authn_dep.access_token_di,
    sns_token: str,
) -> dict:
    obj_in = user_schema.SNSAuthInfoCreate.from_token(
        user_uuid=access_token.user,
        ip=user_ip,
        config_obj=config_obj,
        token=sns_token,
    )
    await user_crud.snsAuthInfoCRUD.create(session=db_session, obj_in=obj_in)
    return {"message": "ok"}
