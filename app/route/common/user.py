import fastapi
import sqlalchemy as sa

import app.const.tag as tag_const
import app.crud.user as user_crud
import app.db.model.user as user_model
import app.dependency.common as common_dep
import app.schema.user as user_schema

router = fastapi.APIRouter(tags=[tag_const.OpenAPITag.USER], prefix="/user")


@router.post(path="/signup/", response_model=user_schema.UserDTO)
async def signup(db_session: common_dep.dbDI, payload: user_schema.UserCreate) -> user_model.User:
    return await user_crud.userCRUD.create(db_session, obj_in=payload)


# @router.post(path="/signin/", response_model=user_schema.UserDTO)
# async def signin(
#     db_session: common_dep.dbDI,
#     payload: user_schema.UserSignIn,
#     user_ip: header_dep.user_ip = None,
#     user_agent: header_dep.user_agent = None,
#     csrf_token: header_dep.csrf_token = None,
# ) -> user_model.User:
#     user = await user_crud.userCRUD.signin(db_session, obj_in=payload)

#     signin_history: user_model.UserSignInHistory = await user_crud.userSignInHistoryCRUD.create(
#         db_session=db_session,
#         obj_in=signin_history_schema.UserSignInHistoryCreate.model_validate({
#             "user_uuid": user.uuid,
#             "ip": user_ip,
#             "user_agent": user_agent,
#         }),
#     )

#     return user


@router.get(path="/{username}/", response_model=user_schema.UserDTO)
async def get_user(db_session: common_dep.dbDI, username: str) -> user_model.User:
    return await user_crud.userCRUD.get_using_query(
        db_session,
        sa.select(user_model.User).where(user_model.User.username == username),
    )
