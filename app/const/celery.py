import enum


class CeleryTaskStatus(enum.StrEnum):
    PENDING = enum.auto()
    STARTED = enum.auto()
    SUCCESS = enum.auto()
    FAILURE = enum.auto()
    RETRY = enum.auto()
    REVOKED = enum.auto()
