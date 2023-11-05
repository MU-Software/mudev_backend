import pathlib as pt
import uuid

import sqlalchemy as sa
import sqlalchemy.ext.asyncio as sa_ext_asyncio
import sqlalchemy.orm as sa_orm
import typing_extensions as tx

SessionType = sa_orm.Session
AsyncSessionType = sa_ext_asyncio.AsyncSession
PossibleSessionType = SessionType | AsyncSessionType

PrimaryKeyType = tx.Annotated[
    uuid.UUID,
    sa_orm.mapped_column(primary_key=True, default=uuid.uuid4, unique=True, index=True, nullable=False),
]

Bool_DTrue = tx.Annotated[bool, sa_orm.mapped_column(default=True, nullable=False)]
Bool_DFalse = tx.Annotated[bool, sa_orm.mapped_column(default=False, nullable=False)]

Str = tx.Annotated[str, sa_orm.mapped_column(nullable=False)]
Str_Unique = tx.Annotated[str, sa_orm.mapped_column(nullable=False, unique=True, index=True)]
Str_Nullable = tx.Annotated[str | None, sa_orm.mapped_column(nullable=True)]

UserFK = tx.Annotated[PrimaryKeyType, sa_orm.mapped_column(sa.ForeignKey("user.uuid"), nullable=False, index=True)]
UserFK_Nullable = tx.Annotated[PrimaryKeyType | None, sa_orm.mapped_column(sa.ForeignKey("user.uuid"), nullable=True)]
FileFK = tx.Annotated[PrimaryKeyType, sa_orm.mapped_column(sa.ForeignKey("file.uuid"), nullable=False)]
FileFK_Nullable = tx.Annotated[PrimaryKeyType | None, sa_orm.mapped_column(sa.ForeignKey("file.uuid"), nullable=True)]

Json = tx.Annotated[dict, sa_orm.mapped_column(sa.JSON)]
Json_Nullable = tx.Annotated[dict | None, sa_orm.mapped_column(sa.JSON)]


class PathType(sa.types.TypeDecorator):
    impl = sa.types.String
    cache_ok = True

    def process_bind_param(self, pathlib_path: pt.Path, dialect) -> str:
        return pathlib_path.absolute().as_posix()

    def process_result_value(self, path_str: str | None, dialect) -> pt.Path | None:
        return pt.Path(path_str) if path_str else None
