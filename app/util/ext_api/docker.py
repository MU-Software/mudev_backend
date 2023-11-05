import datetime
import itertools
import json
import subprocess as sp  # nosec B404


def get_local_image_list(repository: str) -> list[dict]:
    proc = sp.run(  # nosec B603
        args=["docker", "image", "ls", "--format", "{{json .}}", repository],
        check=True,
        capture_output=True,
    )
    return sorted(
        [json.loads(line) for line in proc.stdout.decode().splitlines()],
        key=lambda x: datetime.datetime.strptime(x["CreatedAt"], "%Y-%m-%d %H:%M:%S %z %Z"),
        reverse=True,
    )


def build_docker_cmd(
    *,
    repository: str,
    cmd: list[str],
    env: dict[str, str] | None = None,
    tag: str | None = None,
    use_local_image_if_possible: bool = True,
) -> list[str]:
    docker_cmd = ["docker", "run", "-it", "--rm"]
    docker_env = list(itertools.chain.from_iterable(["--env", f"{k}={v}"] for k, v in env.items() if v))

    if use_local_image_if_possible and (local_repo_img := get_local_image_list(repository)):
        docker_img = [local_repo_img[0]["ID"]]
    else:
        docker_img = [repository + f":{tag}" if tag else ":latest"]

    return docker_cmd + docker_env + docker_img + cmd
