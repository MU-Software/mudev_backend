import typing

import sqlalchemy as sa
import sqlalchemy.orm as sa_orm
import sqlalchemy.sql.schema as sa_schema

M = typing.TypeVar("M", bound=sa_orm.decl_api.DeclarativeBase)


def get_indexes(model: type[sa_orm.decl_api.DeclarativeBase]) -> set[sa_schema.Index]:
    if not hasattr(model.__table__, "indexes"):
        return set()

    return typing.cast(set[sa_schema.Index], model.__table__.indexes)


def get_constraints(model: type[sa_orm.decl_api.DeclarativeBase]) -> set[sa_schema.Constraint]:
    if not hasattr(model.__table__, "constraints"):
        return set()

    return typing.cast(set[sa_schema.Constraint], model.__table__.constraints)


def get_unique_constraints(model: type[sa_orm.decl_api.DeclarativeBase]) -> dict[str, set[sa_schema.Column]]:
    constraints = get_constraints(model)
    indexes = get_indexes(model)

    unique_constraints: dict[str, set[sa_schema.Column]] = {}
    unique_constraints |= {i.name: set(i.columns) for i in constraints if isinstance(i, sa_schema.UniqueConstraint)}
    unique_constraints |= {i.name: set(i.columns) for i in indexes if i.unique}

    return unique_constraints


def get_query_for_finding_unique_violated_constraints(model: type[M], data: dict[str, typing.Any]) -> sa.Select[M]:
    unique_constraints = get_unique_constraints(model)

    if not unique_constraints:
        return sa.select(model).where(sa.false())

    subqueries = []
    for constraint_name, columns in unique_constraints.items():
        if not ({c.name for c in columns} & data.keys()):
            continue
        subquery = sa.exists(sa.select().where(sa.and_(*(c == data[c.name] for c in columns)))).label(constraint_name)
        subqueries.append(subquery)

    return sa.select(*subqueries).limit(1)


def get_column_names(model: type[sa_orm.decl_api.DeclarativeBase]) -> set[str]:
    return set(model.__table__.columns.keys())


def get_not_nullable_columns(model: type[sa_orm.decl_api.DeclarativeBase]) -> set[sa_schema.Column]:
    return {z for z in typing.cast(sa_schema.Column, model.__table__.columns) if not (z.nullable or z.default)}


def get_model_changes(model: sa_orm.decl_api.DeclarativeBase) -> dict[str, list[typing.Any]]:
    """
    Return a dictionary containing changes made to the model since it was
    fetched from the database.

    The dictionary is of the form {'property_name': [old_value, new_value]}

    Example:
        user = get_user_by_id(420)
        >>> '<User id=402 email="business_email@gmail.com">'
        get_model_changes(user)
        >>> {}
        user.email = 'new_email@who-dis.biz'
        get_model_changes(user)
        >>> {'email': ['business_email@gmail.com', 'new_email@who-dis.biz']}

    FROM https://stackoverflow.com/a/56351576
    """
    state = sa.inspect(model)
    changes: dict[str, list[typing.Any]] = {}

    for attr in state.attrs:
        hist = state.get_history(attr.key, True)

        if not hist.has_changes():
            continue

        old_value = hist.deleted[0] if hist.deleted else None
        new_value = hist.added[0] if hist.added else None
        changes[attr.key] = [old_value, new_value]

    return changes


def has_model_changed(model: sa_orm.decl_api.DeclarativeBase) -> bool:
    """
    Return True if there are any unsaved changes on the model.
    """
    return bool(get_model_changes(model))


def create_dynamic_orm_table(
    base: sa_orm.decl_api.DeclarativeMeta,
    engine: sa.engine.base.Engine,
    class_name: str,
    table_name: str,
    columns: typing.Optional[dict[str, typing.Any]] = None,
    mixins: tuple = (),
) -> type[sa_orm.decl_api.DeclarativeMeta]:
    table_attrs: dict = {
        "__tablename__": table_name,
        "__table_args__": {"sqlite_autoincrement": True, "autoload": True, "autoload_with": engine},
    }
    if columns:
        table_attrs.update(columns)

    DynamicORMTable = type(class_name, (*mixins, base), table_attrs)
    return DynamicORMTable


def orm2dict(row: sa_orm.decl_api.DeclarativeBase) -> dict[str, typing.Any]:
    return {column_name: getattr(row, column_name) for column_name in get_column_names(row)}
