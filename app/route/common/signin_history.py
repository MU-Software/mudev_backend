import typing

import fastapi
import sqlalchemy as sa

import app.const.tag as tag_const
import app.crud.user as user_crud
import app.db.model.user as user_model
import app.dependency.authn as authn_dep
import app.dependency.common as common_dep
import app.schema.signin_history as signin_history_schema

router = fastapi.APIRouter(tags=[tag_const.OpenAPITag.USER_HISTORY], prefix="/user/signin-history")


@router.get(path="/", response_model=list[signin_history_schema.UserSignInHistoryDTO])
async def get_signin_history(
    db_session: common_dep.dbDI,
    access_token: authn_dep.access_token_di,
) -> typing.Iterable[user_model.UserSignInHistory]:
    stmt = sa.select(user_model.UserSignInHistory).where(
        user_model.UserSignInHistory.user_uuid == access_token.token_obj.user
    )
    return await user_crud.userSignInHistoryCRUD.get_multi_using_query(db_session, stmt)


@router.delete(path="/{usih_uuid}")
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
