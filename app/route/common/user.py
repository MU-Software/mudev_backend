import fastapi
import sqlalchemy as sa

import app.const.tag as tag_const
import app.crud.user as user_crud
import app.db as db_module
import app.db.model.user as user_model
import app.schema.user as user_schema

router = fastapi.APIRouter(tags=[tag_const.OpenAPITag.USER], prefix="/user")


@router.post(path="/signup/", response_model=user_schema.UserResponse)
async def signup(db_session: db_module.dbDI, payload: user_schema.UserCreate) -> user_model.User:
    return await user_crud.userCRUD.create(db_session, obj_in=payload)


@router.post(path="/signin/", response_model=user_schema.UserResponse)
async def signin(db_session: db_module.dbDI, payload: user_schema.UserSignIn) -> user_model.User:
    return await user_crud.userCRUD.signin(db_session, obj_in=payload)


@router.get(path="/{username}/", response_model=user_schema.UserResponse)
async def get_user(db_session: db_module.dbDI, username: str) -> user_model.User:
    return await user_crud.userCRUD.get_using_query(
        db_session,
        sa.select(user_model.User).where(user_model.User.username == username),
    )
