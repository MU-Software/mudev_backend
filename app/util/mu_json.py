import json

from app.const.time import DATETIME_CLASSES
from app.util.time_util import get_suitable_format


class MUJsonEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, DATETIME_CLASSES):
            return o.strftime(get_suitable_format(o))
        return json.JSONEncoder.default(self, o)


class MUJsonDecoder(json.JSONDecoder):
    def __init__(self, *args, **kwargs):
        json.JSONDecoder.__init__(self, object_hook=self.object_hook, *args, **kwargs)

    def object_hook(self, obj):
        return obj


def dumps(obj, *args, **kwargs):
    if "cls" not in kwargs:
        kwargs["cls"] = MUJsonEncoder
    return json.dumps(obj, *args, **kwargs)


def loads(s, *args, **kwargs):
    if "cls" not in kwargs:
        kwargs["cls"] = MUJsonDecoder
    return json.loads(s, *args, **kwargs)
