import dataclasses
import datetime
import enum

import app.const.cookie as cookie_const


class UserJWTTokenType(enum.Enum):
    @dataclasses.dataclass(frozen=True)
    class UserJWTTokenTypeSetting:
        refresh_delta: datetime.timedelta
        expiration_delta: datetime.timedelta
        cookie_key: cookie_const.CookieKey | None = None

    refresh = UserJWTTokenTypeSetting(
        refresh_delta=datetime.timedelta(days=6),
        expiration_delta=datetime.timedelta(days=7),
        cookie_key=cookie_const.CookieKey.REFRESH_TOKEN,
    )
    access = UserJWTTokenTypeSetting(
        refresh_delta=datetime.timedelta(minutes=15),
        expiration_delta=datetime.timedelta(minutes=30),
    )
