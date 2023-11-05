import functools
import mimetypes
import pathlib as pt
import uuid

import pydantic

import app.util.mu_file as mu_file


class FileCreate(pydantic.BaseModel):
    file: pydantic.FilePath
    data: pydantic.Json | None = None

    private: bool = False
    readable: bool = True
    writable: bool = False

    created_by_uuid: uuid.UUID

    @pydantic.computed_field  # type: ignore[misc]
    @functools.cached_property
    def mimetype(self) -> str | None:
        return mimetypes.guess_type(self.file)[0]

    @pydantic.computed_field  # type: ignore[misc]
    @functools.cached_property
    def hash(self) -> str:
        return mu_file.file_md5(self.file)

    @pydantic.computed_field  # type: ignore[misc]
    @functools.cached_property
    def size(self) -> int:
        return pt.Path(self.file).stat().st_size


class FileUpdate(pydantic.BaseModel):
    data: pydantic.Json | None = None
    private: bool = False
    readable: bool = True
    writable: bool = False
