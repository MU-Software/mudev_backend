import pydantic


class VideoCreate(pydantic.BaseModel):
    youtube_vid: str
    title: str
    data: pydantic.Json | None = None


class VideoUpdate(pydantic.BaseModel):
    ...


class PlaylistCreate(pydantic.BaseModel):
    youtube_pid: str | None = None
    title: str
    data: pydantic.Json | None = None


class PlaylistUpdate(pydantic.BaseModel):
    youtube_pid: str | None = None
    title: str
    data: pydantic.Json | None = None
