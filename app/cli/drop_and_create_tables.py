import typing

import app.config.fastapi as fastapi_config
import app.db as db_module

config_obj = fastapi_config.get_fastapi_setting()


def drop_and_create_tables() -> None:
    if not config_obj.debug:
        raise Exception("This command can only be used in debug mode.")

    # Initialize engine and session pool.
    db_module.init_sync_db()

    with db_module.rdb_sync_session_maker() as session:
        # Drop all tables
        db_module.db_mixin.DefaultModelMixin.metadata.drop_all(
            bind=db_module.rdb_sync_engine.engine,
            checkfirst=True,
        )

        # Create all tables
        db_module.db_mixin.DefaultModelMixin.metadata.create_all(
            bind=db_module.rdb_sync_engine.engine,
            checkfirst=True,
        )

        session.commit()

    # Close engine and session pool.
    db_module.close_sync_db_connection()


cli_patterns: list[typing.Callable] = [drop_and_create_tables] if config_obj.debug else []
