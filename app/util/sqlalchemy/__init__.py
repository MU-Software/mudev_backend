import typing

import sqlalchemy.orm as sa_orm


def get_column_names(model: sa_orm.decl_api.DeclarativeBase) -> set[str]:
    return set(model.__table__.columns.keys())


def orm2dict(row: sa_orm.decl_api.DeclarativeBase) -> dict[str, typing.Any]:
    return {column_name: getattr(row, column_name) for column_name in get_column_names(row)}
