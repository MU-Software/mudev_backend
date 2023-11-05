from __future__ import annotations

import typing

import pydantic
import pydantic_settings


class DBConnectionSetting(pydantic_settings.BaseSettings):
    driver: str
    host: str
    port: int
    username: str
    password: str
    name: str


class SQLAlchemySetting(pydantic_settings.BaseSettings):
    echo: bool = False
    echo_pool: bool = False
    pool_pre_ping: bool = True
    warn_20: bool = True
    dsn: pydantic.PostgresDsn | None = None
    url: str | None = None

    connection: DBConnectionSetting

    model_config = pydantic_settings.SettingsConfigDict(validate_default=True)

    @pydantic.model_validator(mode="after")
    def assemble_url(self) -> typing.Self:
        if self.url:
            return self

        self.dsn = pydantic.PostgresDsn.build(
            scheme=f"postgresql+{self.connection.driver}",
            username=self.connection.username,
            password=self.connection.password,
            host=self.connection.host,
            port=self.connection.port,
            path=self.connection.name,
        )
        self.url = str(self.dsn)
        return self

    def to_sqlalchemy_config(self) -> dict[str, typing.Any]:
        SQLALCHEMY_CONFIG_FIELDS = [
            "echo",
            "echo_pool",
            "pool_pre_ping",
            "url",
        ]
        return self.model_dump(include=SQLALCHEMY_CONFIG_FIELDS)
