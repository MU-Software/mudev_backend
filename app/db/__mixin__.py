import secrets

import sqlalchemy as sa
import sqlalchemy.ext.declarative as sa_dec
import sqlalchemy.orm as sa_orm
import sqlalchemy.sql.schema as sa_schema

import app.db.__type__ as db_types


# I really wanted to use sa_orm.MappedAsDataclass,
# but as created_at and modified_at have default values,
# so it is not possible to use it.
class DefaultModelMixin(sa_orm.DeclarativeBase):
    @sa_dec.declared_attr
    def __tablename__(cls) -> str:
        return cls.__name__.lower()

    metadata = sa_schema.MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )

    uuid: sa_orm.Mapped[db_types.PrimaryKeyType]

    created_at: sa_orm.Mapped[db_types.DateTime] = sa_orm.mapped_column(default=sa.func.now())
    modified_at: sa_orm.Mapped[db_types.DateTime] = sa_orm.mapped_column(default=sa.func.now(), onupdate=sa.func.now())
    deleted_at: sa_orm.Mapped[db_types.DateTime_Nullable]
    commit_id: sa_orm.Mapped[str] = sa_orm.mapped_column(default=secrets.token_hex, onupdate=secrets.token_hex)
