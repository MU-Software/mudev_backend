import sqlalchemy as sa
import sqlalchemy.orm as sa_orm

import app.const.celery as celery_const
import app.db.__mixin__ as db_mixin
import app.db.__type__ as db_types


class Task(db_mixin.DefaultModelMixin):
    celery_task_name: sa_orm.Mapped[str] = sa_orm.mapped_column(sa.String, nullable=False, index=True)
    celery_task_id: sa_orm.Mapped[str] = sa_orm.mapped_column(sa.String, nullable=False, unique=True, index=True)

    args: sa_orm.Mapped[db_types.Json_Nullable]
    kwargs: sa_orm.Mapped[db_types.Json_Nullable]
    startable: sa_orm.Mapped[db_types.Bool_DTrue]
    state: sa_orm.Mapped[celery_const.CeleryTaskStatus] = sa_orm.mapped_column(
        sa.Enum(celery_const.CeleryTaskStatus, native_enum=False),
        nullable=False,
        index=True,
        default=celery_const.CeleryTaskStatus.PENDING,
    )

    created_by: sa_orm.Mapped[db_types.UserFK_Nullable]
