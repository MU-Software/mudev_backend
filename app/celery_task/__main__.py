if __name__ == "__main__":
    import argparse

    import celery

    import app.config.celery as celery_config

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        type=str,
        choices=["worker", "flower", "beat", "healthcheck"],
        help="Celery mode to run.",
    )
    parser.add_argument(
        "--loglevel",
        type=str,
        choices=["debug", "info", "warning", "error", "critical"],
        default="info",
        help="Celery log level.",
    )
    args = parser.parse_args()

    celery_app = celery.Celery()
    celery_app.config_from_object(celery_config.get_celery_setting())
    celery_app.set_default()

    loglevel = f"--loglevel={args.loglevel}"
    match (celery_mode := args.mode):
        case "worker":
            celery_app.worker_main(argv=["worker", loglevel])
        case "flower" | "beat":
            celery_app.start(argv=[celery_mode, loglevel])
        case "healthcheck":
            celery_app.start(argv=["inspect", "ping"])
