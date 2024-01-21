from __future__ import annotations

import json
import typing
import uuid

import pydantic

import app.util.ext_api.youtube as youtube_util


class VideoDTO(pydantic.BaseModel):
    youtube_vid: str
    title: str
    thumbnail_uuid: uuid.UUID
    data: pydantic.Json | dict | None = None


class VideoDownloadRequestPayload(pydantic.BaseModel):
    url: pydantic.AnyHttpUrl = pydantic.Field(exclude=True)

    @pydantic.field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, value: pydantic.AnyHttpUrl) -> str:
        if not youtube_util.extract_vid_from_url(str(value)):
            raise ValueError("invalid youtube url")
        return value

    @pydantic.computed_field  # type: ignore[misc]
    @property
    def youtube_vid(self) -> str:
        return youtube_util.extract_vid_from_url(str(self.url))


class VideoCreate(pydantic.BaseModel):
    youtube_vid: str
    title: str | None = None
    thumbnail_uuid: uuid.UUID | None = None
    data: pydantic.Json | None = None

    __primary_fields__: typing.ClassVar[set[str]] = {"youtube_vid"}

    @pydantic.field_serializer("data")
    def serialize_data(self, v: pydantic.Json | None) -> str | None:
        return json.loads(v) if v else None


class VideoUpdate(pydantic.BaseModel):
    title: str
    thumbnail_uuid: uuid.UUID
    data: pydantic.Json | None = None


class PlaylistCreate(pydantic.BaseModel):
    youtube_pid: str | None = None
    title: str
    data: pydantic.Json | None = None


class PlaylistUpdate(pydantic.BaseModel):
    youtube_pid: str | None = None
    title: str
    data: pydantic.Json | None = None
