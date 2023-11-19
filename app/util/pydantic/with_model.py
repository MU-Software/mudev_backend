from __future__ import annotations

import typing

import pydantic
import sqlalchemy.orm as sa_orm

import app.util.sqlalchemy as sa_util

T = typing.TypeVar("T", bound=sa_orm.decl_api.DeclarativeBase)


class WithSAModelMixin(pydantic.BaseModel, typing.Generic[T]):
    __allowed_data_fields__: set[str] = set()

    @classmethod
    def model_validate_with_orm(cls, *, orm_obj: T, data: dict) -> typing.Type[WithSAModelMixin]:
        if forbidden_data_field := data.keys() - cls.__allowed_data_fields__:
            raise ValueError(f"허용되지 않는 필드가 입력되었습니다: [{', '.join(forbidden_data_field)}]")

        merged_data = {**sa_util.orm2dict(orm_obj), **data}
        return cls.model_validate(merged_data)
