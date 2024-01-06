import dataclasses
import datetime
import enum

import app.const.cookie as cookie_const
import app.util.time_util as time_util


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

    sns_auth_info = UserJWTTokenTypeSetting(
        refresh_delta=datetime.timedelta(hours=1),
        expiration_delta=datetime.timedelta(hours=1),
    )

    def get_exp_from_now(self) -> datetime.datetime:
        return time_util.get_utcnow() + self.value.expiration_delta
