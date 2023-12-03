import dataclasses
import enum

import fastapi
import fastapi.params


class HeaderKey(enum.Enum):
    @dataclasses.dataclass(frozen=True)
    class HeaderKeyData:
        alias: str
        default: str | None = None

    ACCESS_TOKEN = HeaderKeyData(alias="Authorization")
    USER_AGENT = HeaderKeyData(alias="User-Agent")
    REAL_IP = HeaderKeyData(alias="X-Real-IP")
    FORWARDED_FOR = HeaderKeyData(alias="X-Fowarded-For")

    # Custom Header
    TIMEZONE = HeaderKeyData(alias="X-Timezone", default="Etc/UTC")
    TIMEZONE_OFFSET = HeaderKeyData(alias="X-Timezone-Offset", default="+00:00")

    def as_header(self) -> fastapi.params.Header:
        return fastapi.Header(alias=self.value.alias, include_in_schema=False)
