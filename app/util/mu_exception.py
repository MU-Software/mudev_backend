import contextlib
import traceback
import typing

BaseExceptionType = BaseException | typing.Type[BaseException]
T = typing.TypeVar("T")


def raise_(e: BaseExceptionType) -> None:
    raise e


def get_traceback_msg(err: BaseExceptionType) -> str:
    return "".join(traceback.format_exception(err))


def ignore_exception(
    IgnoreException: typing.Type[BaseException] = BaseException, DefaultVal: T = None
) -> typing.Callable:
    # from https://stackoverflow.com/a/2262424
    """Decorator for ignoring exception from a function
    e.g.   @ignore_exception(DivideByZero)
    e.g.2. ignore_exception(DivideByZero)(Divide)(2/0)
    """

    def dec(function: typing.Callable) -> typing.Callable:
        def _dec(*args: tuple, **kwargs: dict) -> T | typing.Any:
            with contextlib.suppress(IgnoreException):
                return function(*args, **kwargs)
            return DefaultVal

        return _dec

    return dec
