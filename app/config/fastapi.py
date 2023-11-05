from __future__ import annotations

import contextlib
import functools
import pathlib as pt
import re
import secrets

import fastapi.openapi.models
import packaging.version
import pydantic
import pydantic_settings
import toml

import app.config.redis as redis_config
import app.config.route as route_config
import app.config.sqlalchemy as sqlalchemy_config

AUTHOR_REGEX = re.compile(r"^(?P<name>[\w\s\d\-]+)\s<(?P<email>.+@.+)>$")


class OpenAPISetting(pydantic_settings.BaseSettings):
    # OpenAPI related configs
    # Only available when restapi_version == "dev"
    docs_url: str | None = "/docs"
    redoc_url: str | None = "/redoc"
    openapi_url: str | None = "/openapi.json"
    openapi_prefix: str | None = ""


class ProjectSetting(OpenAPISetting):
    title: str
    description: str
    version: str
    summary: str | None = None
    terms_of_service: pydantic.HttpUrl | None = None
    contact: fastapi.openapi.models.Contact | None = None
    license: fastapi.openapi.models.License | None = None

    @pydantic.field_validator("version", mode="before")
    @classmethod
    def validate_version(cls, v: str) -> str:
        with contextlib.suppress(packaging.version.InvalidVersion):
            packaging.version.Version(v)
            return v
        raise ValueError(f"Invalid version: {v}")

    @classmethod
    def from_pyproject(cls) -> ProjectSetting:
        project_info: dict = toml.load(pt.Path.cwd() / "pyproject.toml")["tool"]["poetry"]

        contact: fastapi.openapi.models.Contact | None = None
        if (authors := project_info.get("authors", None)) and (homepage := project_info.get("homepage", None)):
            if author_info := AUTHOR_REGEX.match(authors[0]):
                contact = fastapi.openapi.models.Contact(
                    name=author_info.group("name"),
                    email=author_info.group("email"),
                    url=homepage,
                )

        return ProjectSetting(
            title=project_info["name"],
            description=project_info["description"],
            version=project_info["version"],
            contact=contact,
        )


class FastAPISetting(pydantic_settings.BaseSettings):
    host: str
    port: int

    restapi_version: str = "v1"
    secret_key: pydantic.SecretStr = pydantic.SecretStr(secrets.token_hex(16))
    cors_origin: list[pydantic.AnyHttpUrl] = []

    debug: bool = False  # Only available when restapi_version == "dev"
    drop_all_refresh_token_on_load: bool = False

    sqlalchemy: sqlalchemy_config.SQLAlchemySetting
    redis: redis_config.RedisSetting
    project: ProjectSetting = ProjectSetting.from_pyproject()
    route: route_config.RouteSetting

    model_config = pydantic_settings.SettingsConfigDict(extra="ignore")

    @pydantic.model_validator(mode="after")
    def validate_model(self) -> FastAPISetting:
        if self.restapi_version != "dev":
            self.debug = False
            self.drop_all_refresh_token_on_load = False

            self.project.docs_url = None
            self.project.redoc_url = None
            self.project.openapi_url = None
            self.project.openapi_prefix = None

        return self

    def to_fastapi_config(self) -> dict:
        # See fastapi.FastAPI.__init__ keyword arguments for more details
        project_config: dict = self.project.model_dump()
        server_config: dict = {
            "debug": self.debug,
        }
        return project_config | server_config

    def to_uvicorn_config(self) -> dict:
        # See uvicorn.config.Config.__init__ keyword arguments for more details
        return {
            "host": self.host,
            "port": self.port,
            "reload": self.debug,
        }


@functools.lru_cache(maxsize=1)
def get_fastapi_setting() -> FastAPISetting:
    return FastAPISetting(
        _env_file=".env",
        _env_file_encoding="utf-8",
        _env_nested_delimiter="__",
        _case_sensitive=False,
    )
