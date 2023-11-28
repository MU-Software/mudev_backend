import dataclasses
import datetime
import enum

import fastapi
import fastapi.params

import app.const.time as time_const


class CookieKey(enum.Enum):
    @dataclasses.dataclass(frozen=True)
    class CookieKeyData:
        path: str
        expires: datetime.datetime | None = None
        alias: str | None = None

    CSRF_TOKEN = CookieKeyData(path="/", expires=time_const.NEVER_EXPIRE_COOKIE_DATETIME)
    REFRESH_TOKEN = CookieKeyData(path="/user/refresh/")

    def get_name(self) -> str:
        return (self.name if self.value.alias is None else self.value.alias).lower()

    def as_dependency(self) -> fastapi.params.Depends:
        return fastapi.Depends(fastapi.Cookie(alias=self.get_name()))

    def to_cookie_config(self) -> dict[str, str]:
        result: dict[str, str | None] = {
            "key": self.get_name(),
            "path": self.value.path,
            "expires": self.value.expires,
        }
        return {k: v for k, v in result.items() if v is not None}
