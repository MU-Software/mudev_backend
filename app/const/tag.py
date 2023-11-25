import enum


class OpenAPITag(enum.StrEnum):
    HEALTH_CHECK = enum.auto()
    USER = enum.auto()
    USER_HISTORY = enum.auto()
