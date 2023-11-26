import dataclasses
import datetime
import enum


class UserJWTTokenType(enum.Enum):
    @dataclasses.dataclass(frozen=True)
    class UserJWTTokenTypeSetting:
        refresh_delta: datetime.timedelta
        expiration_delta: datetime.timedelta

    refresh = UserJWTTokenTypeSetting(
        refresh_delta=datetime.timedelta(days=6),
        expiration_delta=datetime.timedelta(days=7),
    )
    access = UserJWTTokenTypeSetting(
        refresh_delta=datetime.timedelta(minutes=15),
        expiration_delta=datetime.timedelta(minutes=30),
    )
