import functools
import typing

import pydantic
import pydantic_settings

import app.const.filepath as filepath_const


class ProjectSetting(pydantic_settings.BaseSettings):
    user_content_dir: pydantic.DirectoryPath

    @pydantic.model_validator(mode="after")
    def validate_model(self) -> typing.Self:
        self.user_content_dir = self.user_content_dir.resolve().absolute()
        return self

    @functools.cached_property
    def upload_to(self) -> filepath_const.FileUploadTo:
        return filepath_const.FileUploadTo(self.user_content_dir)
