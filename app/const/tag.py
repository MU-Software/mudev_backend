import enum


class OpenAPITag(enum.StrEnum):
    HEALTH_CHECK = enum.auto()
    USER = enum.auto()
    USER_FILE = enum.auto()
    USER_SIGNIN_HISTORY = enum.auto()

    YTDL = enum.auto()
