import functools
import typing
import uuid

import fastapi.encoders
import pydantic
import sqlalchemy as sa
import sqlalchemy.ext.asyncio as sa_ext_asyncio

import app.db.__mixin__ as db_mixin
import app.db.__type__ as db_types

ModelType = typing.TypeVar("ModelType", bound=db_mixin.DefaultModelMixin)
AwaitableModelType: typing.TypeAlias = typing.Awaitable[ModelType]
PossibleModelType: typing.TypeAlias = ModelType | AwaitableModelType

ModelOrNoneType: typing.TypeAlias = ModelType | None
AwaitableModelOrNoneType = typing.Awaitable[ModelOrNoneType]
PossibleModelOrNoneType: typing.TypeAlias = ModelOrNoneType | AwaitableModelOrNoneType

ModelsType: typing.TypeAlias = sa.ScalarResult[ModelType]
AwaitableModelsType: typing.TypeAlias = typing.Awaitable[ModelsType]
PossibleModelsType: typing.TypeAlias = ModelsType | AwaitableModelsType

AwaitableNoneType: typing.TypeAlias = typing.Awaitable[None]
PossibleNoneType: typing.TypeAlias = None | AwaitableNoneType

CreateSchemaType = typing.TypeVar("CreateSchemaType", bound=pydantic.BaseModel)
UpdateSchemaType = typing.TypeVar("UpdateSchemaType", bound=pydantic.BaseModel)
T = typing.TypeVar("T")


async def commit_and_return(session: sa_ext_asyncio.AsyncSession, db_obj: T) -> T:
    await session.commit()
    return db_obj


class CRUDBase(typing.Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """
    CRUD object with default methods to Create, Read, Update, Delete (CRUD).
    Originally from https://github.com/tiangolo/full-stack-fastapi-postgresql,
    but modified to be asyncronous.

    ## Parameters
    * `model`: A SQLAlchemy model class
    * `schema`: A Pydantic model (schema) class
    """

    def __init__(self, model: typing.Type[ModelType]):
        self.model = model

    @functools.cached_property
    def columns(self) -> set[str]:
        return set(self.model.__table__.columns.keys())

    @functools.cached_property
    def columns_without_uuid(self) -> set[str]:
        return self.columns.copy() - {"uuid"}

    def encode(self, obj: typing.Any) -> dict[str, typing.Any]:
        return fastapi.encoders.jsonable_encoder(
            obj,
            include=self.columns_without_uuid,
            exclude_unset=True,
            exclude_defaults=True,
            sqlalchemy_safe=True,
        )

    @typing.overload
    def get_using_query(self, session: db_types.SessionType, query: sa.Select) -> ModelOrNoneType:
        ...

    @typing.overload
    def get_using_query(  # type: ignore[misc]
        self, session: db_types.AsyncSessionType, query: sa.Select
    ) -> AwaitableModelOrNoneType:
        ...

    def get_using_query(self, session: db_types.PossibleSessionType, query: sa.Select) -> ModelsType:
        return session.scalar(query)

    @typing.overload
    def get(self, session: db_types.SessionType, uuid: str | uuid.UUID) -> ModelOrNoneType:
        ...

    @typing.overload
    def get(  # type: ignore[misc]
        self, session: db_types.AsyncSessionType, uuid: str | uuid.UUID
    ) -> AwaitableModelOrNoneType:
        ...

    def get(self, session: db_types.PossibleSessionType, uuid: str | uuid.UUID) -> PossibleModelOrNoneType:
        return session.scalar(sa.select(self.model).where(self.model.uuid == uuid))

    @typing.overload
    def get_multi_using_query(self, session: db_types.SessionType, query: sa.Select) -> ModelsType:
        ...

    @typing.overload
    def get_multi_using_query(  # type: ignore[misc]
        self, session: db_types.AsyncSessionType, query: sa.Select
    ) -> AwaitableModelsType:
        ...

    def get_multi_using_query(self, session: db_types.PossibleSessionType, query: sa.Select) -> PossibleModelsType:
        return session.scalars(query)

    @typing.overload
    def get_multi(self, session: db_types.SessionType, *, skip: int = 0, limit: int = 100) -> ModelsType:
        ...

    @typing.overload
    def get_multi(  # type: ignore[misc]
        self, session: db_types.AsyncSessionType, *, skip: int = 0, limit: int = 100
    ) -> AwaitableModelsType:
        ...

    def get_multi(
        self, session: db_types.PossibleSessionType, *, skip: int = 0, limit: int = 100
    ) -> PossibleModelsType:
        return session.scalars(sa.select(self.model).offset(skip).limit(limit))

    @typing.overload
    def create(self, session: db_types.SessionType, *, obj_in: CreateSchemaType) -> ModelType:
        ...

    @typing.overload
    def create(  # type: ignore[misc]
        self, session: db_types.AsyncSessionType, *, obj_in: CreateSchemaType
    ) -> AwaitableModelType:
        ...

    def create(self, session: db_types.PossibleSessionType, *, obj_in: CreateSchemaType) -> PossibleModelType:
        db_obj = self.model(**self.encode(obj_in))
        session.add(db_obj)

        if session._is_asyncio:
            return commit_and_return(session, db_obj)
        session.commit()
        return db_obj

    @typing.overload
    def update(self, session: db_types.SessionType, *, db_obj: ModelType, obj_in: UpdateSchemaType) -> ModelType:
        ...

    @typing.overload
    def update(  # type: ignore[misc]
        self, session: db_types.AsyncSessionType, *, db_obj: ModelType, obj_in: UpdateSchemaType
    ) -> AwaitableModelType:
        ...

    def update(
        self, session: db_types.PossibleSessionType, *, db_obj: ModelType, obj_in: UpdateSchemaType
    ) -> PossibleModelType:
        map(lambda item: setattr(db_obj, *item), self.encode(obj_in).items())
        if session._is_asyncio:
            return commit_and_return(session, db_obj)
        session.commit()
        return db_obj

    @typing.overload
    def delete(self, session: db_types.SessionType, *, uuid: str | uuid.UUID) -> ModelsType:
        ...

    @typing.overload
    def delete(  # type: ignore[misc]
        self, session: db_types.AsyncSessionType, *, uuid: str | uuid.UUID
    ) -> AwaitableModelsType:
        ...

    async def delete(self, session: db_types.PossibleSessionType, *, uuid: str | uuid.UUID) -> PossibleModelsType:
        return session.execute(
            sa.update(self.model).where(self.model.uuid == uuid).values(deleted_at=sa.func.now()).returning(self.model)
        )

    @typing.overload
    def hard_delete(self, session: db_types.SessionType, *, uuid: str | uuid.UUID) -> ModelsType:
        ...

    @typing.overload
    def hard_delete(  # type: ignore[misc]
        self, session: db_types.AsyncSessionType, *, uuid: str | uuid.UUID
    ) -> AwaitableModelsType:
        ...

    async def hard_delete(self, session: db_types.PossibleSessionType, *, uuid: str | uuid.UUID) -> PossibleModelsType:
        return session.execute(sa.delete(self.model).where(self.model.uuid == uuid).returning(self.model))
