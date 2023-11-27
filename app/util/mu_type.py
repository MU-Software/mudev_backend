import types
import typing

ContextExitArgType = tuple[type[BaseException], BaseException, typing.Optional[types.TracebackType]]
