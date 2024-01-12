import logging
import typing

import app.config.fastapi as fastapi_config
import app.crud.user as user_crud
import app.db as db_module

logger = logging.getLogger(__name__)
config_obj = fastapi_config.get_fastapi_setting()


def reset_db(do_not_create: bool = False) -> None:
    if not config_obj.debug:
        raise Exception("This command can only be used in debug mode.")

    # Initialize engine and session pool.
    sync_db = db_module.SyncDB(config_obj=config_obj)
    with sync_db as db:
        with db.get_sync_session() as session:
            # Drop all tables
            db_module.db_mixin.DefaultModelMixin.metadata.drop_all(bind=db.engine, checkfirst=True)
            logger.warning("All tables dropped.")

            if not do_not_create:
                # Create all tables
                db_module.db_mixin.DefaultModelMixin.metadata.create_all(bind=db.engine, checkfirst=True)
                logger.warning("All tables created.")

                # Create system user
                user_crud.userCRUD.get_system_user(session=session)
                logger.warning("System user created.")

            session.commit()


cli_patterns: list[typing.Callable] = [reset_db] if config_obj.debug else []
