import datetime
import decimal
import enum
import ipaddress
import json
import typing
import uuid

import app.util.time_util as time_util

JsonType = bool | str | int | float | list | dict | None
PYTHON_JSON_TYPE = (bool, str, int, float, list, dict, type(None))


def obj_to_jsonable_type(obj: typing.Any) -> typing.Any:
    match obj:
        case datetime.datetime() | datetime.date() | datetime.time():
            return time_util.datetime_to_str(obj)
        case enum.Enum():
            return obj.name
        # case typing.Mapping:
        #     obj: typing.Mapping = obj
        #     return dict(obj)
        # case typing.Iterable:
        #     return list(obj)
        # case typing.SupportsBytes:
        #     return obj.__bytes__().decode()
        case (
            datetime.timedelta()
            | ipaddress.IPv4Address()
            | ipaddress.IPv6Address()
            | ipaddress.IPv4Network()
            | ipaddress.IPv6Network()
            | decimal.Decimal()
            | memoryview()
            | uuid.UUID()
        ):
            return str(obj)
    return obj


class MuJSONEncoder(json.JSONEncoder):
    def default(self, obj: typing.Any) -> typing.Any:
        if isinstance((parse_resilt := obj_to_jsonable_type(obj)), PYTHON_JSON_TYPE):
            return parse_resilt

        return json.JSONEncoder.default(self, obj)


def dict_to_jsonable_dict(obj: dict) -> dict[str, JsonType]:
    return json.loads(json.dumps(obj, cls=MuJSONEncoder))
