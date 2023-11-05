import logging.config

import alembic
import sqlalchemy as sa

import app.config.fastapi as app_config
import app.db.__mixin__ as app_db_mixin
import app.db.model as app_db_model  # noqa: F401

fastapi_config_obj = app_config.get_fastapi_setting()
alembic_config_obj = alembic.context.config

if alembic_config_obj.config_file_name is not None:
    # Interpret the config file for Python logging.
    # This line sets up loggers basically.
    logging.config.fileConfig(alembic_config_obj.config_file_name)

# For 'autogenerate' support
target_metadata = app_db_mixin.DefaultModelMixin.metadata


def run_migrations_offline() -> None:
    alembic.context.configure(
        url=fastapi_config_obj.sqlalchemy.url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with alembic.context.begin_transaction():
        alembic.context.run_migrations()


def run_migrations_online() -> None:
    final_config = {
        **alembic_config_obj.get_section(alembic_config_obj.config_ini_section, {}),
        "sqlalchemy.url": fastapi_config_obj.sqlalchemy.url,
    }
    connectable = sa.engine_from_config(
        final_config,
        prefix="sqlalchemy.",
        poolclass=sa.pool.NullPool,
    )

    with connectable.connect() as connection:
        alembic.context.configure(connection=connection, target_metadata=target_metadata)
        with alembic.context.begin_transaction():
            alembic.context.run_migrations()


if alembic.context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
