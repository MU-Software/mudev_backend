import datetime
import itertools
import json
import logging
import pathlib as pt
import subprocess as sp  # nosec B404

import docker
import paramiko

logger = logging.getLogger(__name__)


def is_container() -> bool:
    cgroup = pt.Path("/proc/self/cgroup")
    return pt.Path("/.dockerenv").is_file() or cgroup.is_file() and "docker" in cgroup.read_text()


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


def get_secret_file(secret_name: str) -> pt.Path | None:
    return secret_file if (secret_file := (pt.Path("/run/secrets") / secret_name)).exists() else None


def run_cmd_on_host(cmd: list[str]) -> tuple[str, str]:
    username_file, pkey_file = get_secret_file("host_username"), get_secret_file("host_id_rsa")
    if not (username_file and pkey_file and username_file.exists() and pkey_file.exists()):
        raise RuntimeError("Username or private key secret not found.")

    username = username_file.read_text().strip()
    pkey = paramiko.RSAKey.from_private_key(pkey_file.open())

    paramiko_client = paramiko.SSHClient()
    paramiko_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # nosec B507
    paramiko_client.connect("host.docker.internal", username=username, pkey=pkey)

    logger.warning(f"Running command on host: \n[{', '.join(cmd)}]")
    ssh_stdin, ssh_stdout, ssh_stderr = paramiko_client.exec_command(" ".join(cmd))  # nosec B601
    ssh_stdin.close()

    stdout = "".join(ssh_stdout.readlines())
    stderr = "".join(ssh_stderr.readlines())

    paramiko_client.close()

    return stdout, stderr


def resolve_container_path_to_host(docker_path: pt.Path) -> pt.Path:
    container_id = pt.Path("/etc/hostname").read_text().strip()
    continer_info = docker.from_env().api.inspect_container(container_id)
    container_host_mount_map = {
        pt.Path(mount["Destination"]): pt.Path(mount["Source"]) for mount in continer_info["Mounts"]
    }

    for container_path, host_path in container_host_mount_map.items():
        if container_path in docker_path.parents:
            return host_path / docker_path.relative_to(container_path)
    raise FileNotFoundError(f"Cannot resolve docker path to host path: {docker_path}")
