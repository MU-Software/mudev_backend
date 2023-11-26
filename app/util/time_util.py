import contextlib
import datetime
import typing

import app.const.time as time_const


def get_suitable_format(o: typing.Any) -> str:
    if isinstance(o, datetime.datetime):
        return time_const.DATETIME_FORMAT
    elif isinstance(o, datetime.date):
        return time_const.DATE_FORMAT
    elif isinstance(o, datetime.time):
        return time_const.TIME_WITH_MICROSECOND_FORMAT

    raise ValueError(f"Unknown type: {type(o)}")


def datetime_to_str(o: datetime.datetime | datetime.date | datetime.time) -> str:
    return o.strftime(get_suitable_format(o))


def get_utcnow(drop_microsecond: bool = False) -> datetime.datetime:
    # python's datetime.datetime.utcnow() does not contains timezone info.
    result = datetime.datetime.now(tz=time_const.UTC)
    if drop_microsecond:
        result = result.replace(microsecond=0)
    return result


def date_to_time(x: int) -> int:
    return x * 24 * 60 * 60


def hour_to_time(x: int) -> int:
    return x * 60 * 60


def as_utctime(x: datetime.datetime, just_replace: bool = False) -> datetime.datetime:
    if just_replace:
        return x.replace(tzinfo=time_const.UTC)
    return x.astimezone(time_const.UTC)


def as_utc_timestamp(x: datetime.datetime, just_replace: bool = False) -> float:
    return as_utctime(x, just_replace=just_replace).timestamp()


def try_parse_datetime_str(
    x: str,
    try_format: typing.Iterable[str] = time_const.DATETIME_PARSE_FORMATS,
) -> datetime.datetime | None:
    for fmt in try_format:
        with contextlib.suppress(ValueError):
            return datetime.datetime.strptime(x, fmt)
    return None


DateTimeableType = datetime.datetime | datetime.date | datetime.time | datetime.timedelta | str | int | float | None


def try_parse_datetime(
    x: DateTimeableType = None,
    try_format: typing.Iterable[str] = time_const.DATETIME_PARSE_FORMATS,
    raise_if_not_parseable: bool = False,
) -> datetime.datetime | None:
    if not x:
        return None

    if isinstance(x, datetime.datetime):
        return x

    if isinstance(x, datetime.date):
        return datetime.datetime.combine(x, datetime.time())

    if isinstance(x, datetime.time):
        return datetime.datetime.combine(datetime.date.today(), x)

    if isinstance(x, str):
        return try_parse_datetime_str(x, try_format=try_format)

    if isinstance(x, (int, float)):
        return datetime.datetime.fromtimestamp(x)

    if isinstance(x, datetime.timedelta):
        return datetime.datetime.now() + x

    if raise_if_not_parseable:
        raise ValueError(f"Cannot parse {x} as datetime.")

    return None


def try_parse_date(
    x: DateTimeableType = None,
    try_format: typing.Iterable[str] = time_const.DATE_PARSE_FORMATS,
    raise_if_not_parseable: bool = False,
) -> datetime.date | None:
    if parsed_result := try_parse_datetime(x, try_format=try_format, raise_if_not_parseable=raise_if_not_parseable):
        return parsed_result.date()
    return None


def try_parse_time(
    x: DateTimeableType,
    try_format: typing.Iterable[str] = time_const.TIME_PARSE_FORMATS,
    raise_if_not_parseable: bool = False,
) -> datetime.time | None:
    if parsed_result := try_parse_datetime(x, try_format=try_format, raise_if_not_parseable=raise_if_not_parseable):
        return parsed_result.time()
    return None
