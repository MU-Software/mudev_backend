import contextlib
import socket


def islocalhost(host: str) -> bool:
    with contextlib.suppress(socket.gaierror):
        return socket.gethostbyaddr(host)[2] in (["127.0.0.1"], ["::1"])
    return False


def find_free_port():
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]
