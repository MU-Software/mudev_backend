if __name__ == "__main__":
    import sys

    import celery

    import app.config.celery as celery_config

    celery_app = celery.Celery()
    celery_app.config_from_object(celery_config.get_celery_setting())
    celery_app.set_default()

    if len(sys.argv) >= 2 and sys.argv[1] == "flower":
        celery_app.start(argv=["flower", "--loglevel=info"])
    elif len(sys.argv) >= 2 and sys.argv[1] == "healthcheck":
        celery_app.start(argv=["inspect", "ping"])
    else:
        celery_app.worker_main(argv=["worker", "--loglevel=info"])
