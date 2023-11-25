import itertools
import os
import subprocess as sp  # nosec B404
import typing

import app.config.fastapi as fastapi_config
import app.util.ext_api.docker as docker_util
import app.util.network as network_util

config_obj = fastapi_config.get_fastapi_setting()


def redis_shell(use_docker: bool = True) -> None:
    environ: dict[str, str] = {
        "TZ": "Asia/Seoul",
        "REDISCLI_AUTH": config_obj.redis.password or "",
    }
    kwargs: dict[str, str] = {
        "--user": config_obj.redis.username or "",
        "-h": config_obj.redis.host,
        "-p": str(config_obj.redis.port),
        "-n": str(config_obj.redis.db),
    }
    if use_docker and network_util.islocalhost(kwargs["-h"]):
        kwargs["-h"] = "host.docker.internal"

    redis_cli: list[str] = ["redis-cli"]
    redis_args: list[str] = list(itertools.chain.from_iterable([k, v] for k, v in kwargs.items() if v))
    redis_exec: list[str] = redis_cli + redis_args
    if use_docker:
        redis_exec = docker_util.build_docker_cmd(repository="redis", cmd=redis_exec, env=environ)

    sp.run(args=redis_exec, env={**os.environ.copy(), **environ})  # nosec B603


cli_patterns: list[typing.Callable] = [redis_shell]
