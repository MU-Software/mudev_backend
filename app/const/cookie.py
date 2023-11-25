import dataclasses
import datetime
import enum

import app.const.time as time_const


class CookieKey(enum.Enum):
    @dataclasses.dataclass(frozen=True)
    class CookieKeyData:
        path: str
        expires: datetime.datetime | None = None

    CSRF_TOKEN = CookieKeyData(path="/", expires=time_const.NEVER_EXPIRE_COOKIE_DATETIME)
    REFRESH_TOKEN = CookieKeyData(path="/user/refresh/")

    def to_cookie_config(self) -> dict[str, str]:
        result: dict[str, str | None] = {
            "key": self.name,
            "path": self.value.path,
            "expires": self.value.expires,
        }
        return {k: v for k, v in result.items() if v is not None}
