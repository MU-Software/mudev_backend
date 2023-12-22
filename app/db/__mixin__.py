import re
import secrets
import typing

import sqlalchemy as sa
import sqlalchemy.ext.declarative as sa_dec
import sqlalchemy.orm as sa_orm
import sqlalchemy.sql.schema as sa_schema

import app.db.__type__ as db_types
import app.util.sqlalchemy as sa_util


class NCType(typing.NamedTuple):
    name: str
    regex: re.Pattern


NCKey = typing.Literal["ix", "uq", "ck", "fk", "pk"]


NAMING_CONVENTION_DICT: dict[NCKey, NCType] = {
    "ix": NCType(
        "ix_%(column_0_label)s",
        re.compile(r"^ix_(?P<table_name>.+)_(?P<column_0_name>.+)$"),
    ),
    "uq": NCType(
        "uq_%(table_name)s_%(column_0_name)s",
        re.compile(r"^uq_(?P<table_name>.+)_(?P<column_0_name>.+)$"),
    ),
    "ck": NCType(
        "ck_%(table_name)s_%(constraint_name)s",
        re.compile(r"^ck_(?P<table_name>.+)_(?P<constraint_name>.+)$"),
    ),
    "fk": NCType(
        "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        re.compile(r"^fk_(?P<table_name>.+)_(?P<column_0_name>.+)_(?P<referred_table_name>.+)$"),
    ),
    "pk": NCType(
        "pk_%(table_name)s",
        re.compile(r"^pk_(?P<table_name>.+)$"),
    ),
}


# I really wanted to use sa_orm.MappedAsDataclass,
# but as created_at and modified_at have default values,
# so it is not possible to use it.
class DefaultModelMixin(sa_orm.DeclarativeBase):
    @sa_dec.declared_attr
    def __tablename__(cls) -> str:
        return cls.__name__.lower()

    metadata = sa_schema.MetaData(naming_convention={k: v.name for k, v in NAMING_CONVENTION_DICT.items()})

    uuid: sa_orm.Mapped[db_types.PrimaryKeyType]

    created_at: sa_orm.Mapped[db_types.DateTime] = sa_orm.mapped_column(insert_default=sa.func.now())
    modified_at: sa_orm.Mapped[db_types.DateTime] = sa_orm.mapped_column(
        insert_default=sa.func.now(), onupdate=sa.func.now()
    )
    deleted_at: sa_orm.Mapped[db_types.DateTime_Nullable]
    commit_id: sa_orm.Mapped[str] = sa_orm.mapped_column(default=secrets.token_hex, onupdate=secrets.token_hex)

    @property
    def dict(self) -> typing.Dict[str, typing.Any]:
        return sa_util.orm2dict(self)

    @classmethod
    def get_model(cls, model_name: str) -> sa_orm.decl_api.DeclarativeBase:
        return typing.cast(sa_orm.decl_api.DeclarativeBase, cls.metadata.tables[model_name])
