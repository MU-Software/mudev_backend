import logging
import typing

import app.config.fastapi as fastapi_config
import app.db as db_module

logger = logging.getLogger(__name__)
config_obj = fastapi_config.get_fastapi_setting()


def drop_and_create_tables() -> None:
    if not config_obj.debug:
        raise Exception("This command can only be used in debug mode.")

    # Initialize engine and session pool.
    with db_module.sync_db as sync_db:
        with sync_db.get_sync_session() as session:
            # Drop all tables
            db_module.db_mixin.DefaultModelMixin.metadata.drop_all(bind=sync_db.engine, checkfirst=True)
            logger.warning("All tables dropped.")

            # Create all tables
            db_module.db_mixin.DefaultModelMixin.metadata.create_all(bind=sync_db.engine, checkfirst=True)
            logger.warning("All tables created.")

            session.commit()


cli_patterns: list[typing.Callable] = [drop_and_create_tables] if config_obj.debug else []
