import datetime

import app.const.time as time_const


def get_suitable_format(o):
    if isinstance(o, datetime.datetime):
        return time_const.DATETIME_FORMAT
    elif isinstance(o, datetime.date):
        return time_const.DATE_FORMAT
    elif isinstance(o, datetime.time):
        return time_const.TIME_FORMAT

    raise ValueError(f"Unknown type: {type(o)}")


def get_utcnow(drop_microsecond: bool = False) -> datetime.datetime:
    # python's datetime.datetime.utcnow() does not contains timezone info.
    result = datetime.datetime.now(tz=time_const.UTC)
    if drop_microsecond:
        result = result.replace(microsecond=0)
    return result


def date_to_time(x: int):
    return x * 24 * 60 * 60


def hour_to_time(x: int):
    return x * 60 * 60


def as_utctime(x: datetime.datetime, just_replace: bool = False):
    if just_replace:
        return x.replace(tzinfo=time_const.UTC)
    return x.astimezone(time_const.UTC)


def as_utc_timestamp(x: datetime.datetime, just_replace: bool = False):
    return as_utctime(x, just_replace=just_replace).timestamp()
