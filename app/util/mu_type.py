import types
import typing

import pydantic_settings

ContextExitArgType = tuple[type[BaseException], BaseException, typing.Optional[types.TracebackType]]


class BaseConnectedResource(typing.Protocol):
    config_obj: pydantic_settings.BaseSettings

    def __init__(self, config_obj: pydantic_settings.BaseSettings) -> None:
        self.config_obj = config_obj


class SyncConnectedResource(BaseConnectedResource, typing.Protocol):
    def open(self) -> typing.Self: ...

    def close(self) -> None: ...

    def get_sync_session(self) -> typing.Any: ...

    def __enter__(self) -> typing.Self:
        return self.open()

    def __exit__(self, *args: ContextExitArgType) -> None:
        self.close()


class AsyncConnectedResource(BaseConnectedResource, typing.Protocol):
    def aopen(self) -> typing.Awaitable[typing.Self]: ...

    def aclose(self) -> typing.Awaitable[None]: ...

    def get_async_session(self) -> typing.AsyncContextManager[typing.AsyncGenerator[typing.Any, None]]: ...

    async def __aenter__(self) -> typing.Self:
        return await self.aopen()

    async def __aexit__(self, *args: ContextExitArgType) -> None:
        return await self.aclose()
