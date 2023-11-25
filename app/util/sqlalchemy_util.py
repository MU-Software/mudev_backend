import typing

import sqlalchemy as sql
import sqlalchemy.ext.declarative as sqldec
import sqlalchemy.orm as sqlorm


def get_model_changes(model: sqlorm.DeclarativeBase) -> dict[str, list[typing.Any]]:
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
    state = sql.inspect(model)
    changes: dict[str, list[typing.Any]] = {}

    for attr in state.attrs:
        hist = state.get_history(attr.key, True)

        if not hist.has_changes():
            continue

        old_value = hist.deleted[0] if hist.deleted else None
        new_value = hist.added[0] if hist.added else None
        changes[attr.key] = [old_value, new_value]

    return changes


def has_model_changed(model: sqlorm.DeclarativeBase) -> bool:
    """
    Return True if there are any unsaved changes on the model.
    """
    return bool(get_model_changes(model))


def create_dynamic_orm_table(
    base: sqldec.DeclarativeMeta,
    engine: sql.engine.base.Engine,
    class_name: str,
    table_name: str,
    columns: typing.Optional[dict[str, typing.Any]] = None,
    mixins: tuple = (),
) -> type[sqlorm.DeclarativeMeta]:
    table_attrs: dict = {
        "__tablename__": table_name,
        "__table_args__": {
            "sqlite_autoincrement": True,
            "autoload": True,
            "autoload_with": engine,
        },
    }
    if columns:
        table_attrs.update(columns)

    DynamicORMTable = type(class_name, (*mixins, base), table_attrs)
    return DynamicORMTable
