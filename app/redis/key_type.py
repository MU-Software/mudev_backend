import enum


class RedisKeyType(enum.StrEnum):
    # RedisKeyType's enum values are string, because this will be used on Redis key.
    # This is intended and must not be used on DB column type.
    EMAIL_VERIFICATION = enum.auto()
    EMAIL_PASSWORD_RESET = enum.auto()
    TOKEN_REVOKED = enum.auto()

    def as_redis_key(self, value: str):
        return f"{self.value}:{value}"
