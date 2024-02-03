import functools
import typing
import uuid

import pydantic
import sqlalchemy as sa
import sqlalchemy.ext.asyncio as sa_ext_asyncio

import app.const.error as error_const
import app.db.__mixin__ as db_mixin
import app.db.__type__ as db_types
import app.util.sqlalchemy as sa_util

T = typing.TypeVar("T")
M = typing.TypeVar("M", bound=db_mixin.DefaultModelMixin)
CreateSchema = typing.TypeVar("CreateSchema", bound=pydantic.BaseModel)
UpdateSchema = typing.TypeVar("UpdateSchema", bound=pydantic.BaseModel)


async def commit_and_return(session: sa_ext_asyncio.AsyncSession, db_obj: T) -> T:
    await session.commit()
    return db_obj


class CRUDBase(typing.Generic[M, CreateSchema, UpdateSchema]):
    """
    CRUD object with default methods to Create, Read, Update, Delete (CRUD).
    Originally from https://github.com/tiangolo/full-stack-fastapi-postgresql,
    but modified to be asyncronous.

    ## Parameters
    * `model`: A SQLAlchemy model class
    * `schema`: A Pydantic model (schema) class
    """

    def __init__(self, model: typing.Type[M]):
        self.model = model

    @functools.cached_property
    def columns(self) -> set[str]:
        return set(self.model.__table__.columns.keys())

    @functools.cached_property
    def columns_without_uuid(self) -> set[str]:
        return self.columns - {"uuid"}

    @typing.overload
    def get_using_query(self, session: db_types.Ss, query: sa.Select) -> M | None: ...

    @typing.overload
    def get_using_query(  # type: ignore[misc]
        self, session: db_types.As, query: sa.Select
    ) -> typing.Awaitable[M | None]: ...

    def get_using_query(self, session: db_types.Ps, query: sa.Select) -> (M | None) | typing.Awaitable[M | None]:
        return session.scalar(query)

    @typing.overload
    def get(self, session: db_types.Ss, uuid: uuid.UUID) -> M | None: ...

    @typing.overload
    def get(self, session: db_types.As, uuid: uuid.UUID) -> typing.Awaitable[M | None]:  # type: ignore[misc]
        ...

    def get(self, session: db_types.Ps, uuid: uuid.UUID) -> (M | None) | typing.Awaitable[M | None]:
        return session.scalar(sa.select(self.model).where(self.model.uuid == uuid))

    @typing.overload
    def get_multi_using_query(
        self, session: db_types.Ss, query: sa.Select, *, skip: int | None = None, limit: int | None = None
    ) -> sa.ScalarResult[M]: ...

    @typing.overload
    def get_multi_using_query(  # type: ignore[misc]
        self, session: db_types.As, query: sa.Select, *, skip: int | None = None, limit: int | None = None
    ) -> typing.Awaitable[sa.ScalarResult[M]]: ...

    def get_multi_using_query(
        self, session: db_types.Ps, query: sa.Select, *, skip: int | None = None, limit: int | None = None
    ) -> sa.ScalarResult[M] | typing.Awaitable[sa.ScalarResult[M]]:
        if skip:
            query = query.offset(skip)
        if limit:
            query = query.limit(limit)
        return session.scalars(query)

    @typing.overload
    def create(self, session: db_types.Ss, obj_in: CreateSchema) -> M: ...

    @typing.overload
    def create(self, session: db_types.As, obj_in: CreateSchema) -> typing.Awaitable[M]:  # type: ignore[misc]
        ...

    def create(self, session: db_types.Ps, obj_in: CreateSchema) -> M | typing.Awaitable[M]:
        db_obj: M = self.model(**obj_in.model_dump())

        nulled_columns: set[str] = {k for k, v in sa_util.orm2dict(db_obj).items() if v is None}
        not_nullable_columns: set[str] = {c.name for c in sa_util.get_not_nullable_columns(self.model)}
        if nn_failed_columns := not_nullable_columns & nulled_columns:
            error_const.ErrorStruct.raise_multiple(
                [
                    error_const.DBValueError.DB_NOT_NULL_CONSTRAINT_ERROR(
                        loc=["body", column_name],
                        input=getattr(obj_in, column_name),
                    )
                    for column_name in nn_failed_columns
                ]
            )
        session.add(db_obj)

        if session._is_asyncio:
            return commit_and_return(session, db_obj)
        session.commit()
        return db_obj

    def get_or_create(self, session: db_types.Ss, obj_in: CreateSchema) -> tuple[M, bool]:
        primary_fields: set[str]
        if not (primary_fields := getattr(obj_in, "__primary_fields__", None)):
            raise ValueError("obj_in must have __primary_fields__ attribute to use get_or_create")

        stmt_filter = sa.and_(*[getattr(self.model, field) == getattr(obj_in, field) for field in primary_fields])
        if db_obj := self.get_using_query(session, sa.select(self.model).where(stmt_filter)):
            return db_obj, False
        return self.create(session, obj_in=obj_in), True

    async def get_or_create_async(self, session: db_types.As, obj_in: CreateSchema) -> tuple[M, bool]:
        primary_fields: set[str]
        if not (primary_fields := getattr(obj_in, "__primary_fields__", None)):
            raise ValueError("obj_in must have __primary_fields__ attribute to use get_or_create")

        stmt_filter = sa.and_(*[getattr(self.model, field) == getattr(obj_in, field) for field in primary_fields])
        if db_obj := await self.get_using_query(session, sa.select(self.model).where(stmt_filter)):
            return db_obj, False
        return await self.create(session, obj_in=obj_in), True

    @typing.overload
    def update(self, session: db_types.Ss, db_obj: M, obj_in: UpdateSchema) -> M: ...

    @typing.overload
    def update(  # type: ignore[misc]
        self, session: db_types.As, db_obj: M, obj_in: UpdateSchema
    ) -> typing.Awaitable[M]: ...

    def update(self, session: db_types.Ps, db_obj: M, obj_in: UpdateSchema) -> M | typing.Awaitable[M]:
        # The reason why we get db_obj instead of uuid is
        # because if we get uuid, we cannot support both sync and async as we need to call self.get first.
        for k, v in obj_in.model_dump().items():
            setattr(db_obj, k, v)

        if session._is_asyncio:
            return commit_and_return(session, db_obj)
        session.commit()
        return db_obj

    @typing.overload
    def delete(self, session: db_types.Ss, uuid: uuid.UUID) -> sa.ScalarResult[M]: ...

    @typing.overload
    def delete(  # type: ignore[misc]
        self, session: db_types.As, uuid: uuid.UUID
    ) -> typing.Awaitable[sa.ScalarResult[M]]: ...

    def delete(
        self, session: db_types.Ps, uuid: uuid.UUID
    ) -> sa.ScalarResult[M] | typing.Awaitable[sa.ScalarResult[M]]:
        return session.execute(
            sa.update(self.model).where(self.model.uuid == uuid).values(deleted_at=sa.func.now()).returning(self.model)
        )

    @typing.overload
    def hard_delete(self, session: db_types.Ss, uuid: uuid.UUID) -> sa.ScalarResult[M]: ...

    @typing.overload
    def hard_delete(  # type: ignore[misc]
        self, session: db_types.As, uuid: uuid.UUID
    ) -> typing.Awaitable[sa.ScalarResult[M]]: ...

    def hard_delete(
        self, session: db_types.Ps, uuid: uuid.UUID
    ) -> sa.ScalarResult[M] | typing.Awaitable[sa.ScalarResult[M]]:
        return session.execute(sa.delete(self.model).where(self.model.uuid == uuid).returning(self.model))


class EmptySchema(pydantic.BaseModel): ...  # noqa: E701
