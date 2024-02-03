import functools

import pydantic
import pydantic_settings

import app.const.filepath as filepath_const


class SSCoProjectSetting(pydantic_settings.BaseSettings):
    telegram_bot_token: pydantic.SecretStr


class ProjectSetting(pydantic_settings.BaseSettings):
    frontend_domain: pydantic.HttpUrl
    backend_domain: pydantic.HttpUrl
    user_content_dir: pydantic.DirectoryPath

    ssco: SSCoProjectSetting

    @pydantic.field_validator("user_content_dir", mode="before")
    def validate_user_content_dir(self, value: pydantic.DirectoryPath) -> pydantic.DirectoryPath:
        return value.resolve().absolute()

    @functools.cached_property
    def upload_to(self) -> filepath_const.FileUploadTo:
        return filepath_const.FileUploadTo(self.user_content_dir)
