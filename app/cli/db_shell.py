import itertools
import os
import subprocess as sp  # nosec B404
import typing

import app.config.fastapi as fastapi_config
import app.util.ext_api.docker as docker_util
import app.util.network as network_util

config_obj = fastapi_config.get_fastapi_setting()


def db_shell(use_docker: bool = True):
    environ: dict[str, str] = {
        "TZ": "Asia/Seoul",
        "PGPASSWORD": config_obj.sqlalchemy.connection.password,
    }
    kwargs: dict[str, str] = {
        "-U": config_obj.sqlalchemy.connection.username,
        "-h": config_obj.sqlalchemy.connection.host,
        "-p": str(config_obj.sqlalchemy.connection.port),
        "-d": config_obj.sqlalchemy.connection.name,
    }
    if use_docker and network_util.islocalhost(kwargs["-h"]):
        kwargs["-h"] = "host.docker.internal"

    psql_cli: list[str] = ["psql"]
    psql_args: list[str] = list(itertools.chain.from_iterable([k, v] for k, v in kwargs.items() if v))
    psql_exec: list[str] = psql_cli + psql_args
    if use_docker:
        psql_exec = docker_util.build_docker_cmd(repository="postgres", cmd=psql_exec, env=environ)

    sp.run(args=psql_exec, env={**os.environ.copy(), **environ})  # nosec B603


cli_patterns: list[typing.Callable] = [db_shell]
