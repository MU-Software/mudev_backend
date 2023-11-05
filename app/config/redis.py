import typing

import pydantic
import pydantic_settings


class RedisSetting(pydantic_settings.BaseSettings):
    username: str | None = None
    password: str | None = None
    host: str
    port: int = 6379
    db: int = 0
    dsn: pydantic.RedisDsn | None = None
    uri: str | None = None

    model_config = pydantic_settings.SettingsConfigDict(validate_default=True)

    @pydantic.model_validator(mode="after")
    def assemble_uri(self) -> typing.Self:
        if isinstance(self.uri, str):
            return self

        self.dsn = pydantic.RedisDsn.build(
            scheme="redis",
            username=self.username,
            password=self.password,
            host=self.host,
            port=self.port,
            path=str(self.db),
        )
        self.uri = str(self.dsn)
        return self
