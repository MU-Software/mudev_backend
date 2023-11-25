import typing

import IPython


def py_shell() -> None:
    """
    IPython shell을 실행합니다.
    """
    IPython.start_ipython(argv=[])


cli_patterns: list[typing.Callable] = [py_shell]
