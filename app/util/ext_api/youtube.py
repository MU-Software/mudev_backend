from __future__ import annotations

import base64
import contextlib
import functools
import importlib.metadata
import io
import json
import logging
import pathlib as pt
import re
import typing
import zlib

import googleapiclient.discovery as google_api_discovery
import PIL.Image
import pydantic
import requests
import yt_dlp

logger = logging.getLogger(__name__)

VIDEO_REGEX = re.compile(
    r"(?:youtube\.com|youtu\.be)/(?:[\w-]+\?v=|embed/|v/|shorts/)?([\w-]{11})", flags=re.IGNORECASE
)
PLAYLIST_REGEX = re.compile(r"(?:youtube\.com|youtu\.be)\/(?:[\w\-\?\&\=\/]+[?&])list=([\w-]{34})", flags=re.IGNORECASE)

POSSIBLE_THUMBNAIL_QUALITY: list[str] = [
    "maxresdefault",  # Best quality
    "hqdefault",
    "sddefault",
    "mqdefault",
    "default",  # Worst quality
]
THUMBNAIL_B64: bytes = (
    b"eJztmT1oFFEUhQ/R+EcaQVGCVbQQe2Nj8VIExD5CIOCzSWFjb8SfQqK1qI2kiJWFrQoRFQwkIIaAUREsYoggSBLSCQH1XK4LE9x9M3Pf7M5C3oGv"
    b"Wcid82123sy8AVJSdlT2k+PkLLlArpBbZJz01dirkWb97pJp8pJ8JBvkT4AV0t/F/cowVXF/6T5DtirsWITNCh32ka8d7t9gq0KP4Zocqva43YG+"
    b"v8kPskjmM5//rNDjUWTHdej5L+eXrAd3oOvDCHS9GCC9meO5zN8ud8CjbL+icWiPx7XM3AVyDLZ+RePQHg+fmfumwrmt4pA8QvFIHpY4JI9QPJKH"
    b"JQ7JIxSP5GGJQ/IIxSN5WOKQPELxSB7Ncgq61ybPX0vkE3kN3T86g+73OEqeQp/FQ8/BC+hejxPkG8L9m7Fsbv1/POI89kD3QSx7FCtRzbfHI85j"
    b"DDYHYSOq+fZ4xHk8ht3jV4njyN7zeXKTPCD3oHskQ9B9kViP5xEeqwXm7yU3yFrOnOz3afF4GOHxLGf2YfLeMNfi4SI8Lgbm7iJzxrkWD8kTw7Fm"
    b"/3VtlUtGB2HR6HEA+hspepx35FDOzJjz7rvRQ9JDLkOvCa3my/76BPSak5fPER5fIjwa2Q09Z65C18b75Do5B107i+at0UGYjteoLPJ/s3qM1tC3"
    b"VQ5CrwtlHeQ+tJ3vCywZhL6HKeog96oDtTTNj7xLlnfeof7yrCBr/5GaOpbJaTJJXkHfk30gL6D3LCdr7JWS0pH8BQ5Of7c="
)
THUMBNAIL_BYTES: bytes = zlib.decompress(base64.b64decode(THUMBNAIL_B64))
THUMBNAIL_IMG: PIL.Image.Image = PIL.Image.frombytes(data=THUMBNAIL_BYTES, size=(50, 50), mode="RGBA")


def extract_vid_from_url(url: str) -> str | None:
    if match := VIDEO_REGEX.search(url):
        return match.group(1)
    return None


def extract_pid_from_url(url: str) -> str | None:
    if match := PLAYLIST_REGEX.search(url):
        return match.group(1)
    return None


def get_thumbnail_bytes(video_id: str) -> bytes:
    for qualiy in POSSIBLE_THUMBNAIL_QUALITY:
        with contextlib.suppress(requests.exceptions.RequestException):
            response = requests.get(f"https://i.ytimg.com/vi/{video_id}/{qualiy}.jpg", timeout=5)
            if response.ok:
                return response.content

    return THUMBNAIL_BYTES


def download_thumbnail(video_id: str, save_dir: pt.Path) -> pt.Path:
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / "thumbnail.png"
    save_path.unlink(missing_ok=True)
    PIL.Image.open(io.BytesIO(get_thumbnail_bytes(video_id))).save(save_path, format="PNG")
    return save_path


def get_video_ids_from_playlist_id(playlist_id: str, google_api_key: str) -> set[str]:
    playlist_items_api = google_api_discovery.build("youtube", "v3", developerKey=google_api_key).playlistItems()
    video_ids: set[str] = set()
    page_token: str | None = None

    while True:
        items: dict = playlist_items_api.list(part="snippet", playlistId=playlist_id, pageToken=page_token).execute()
        video_ids.update(item["snippet"]["resourceId"]["videoId"] for item in items["items"])
        if not (page_token := items.get("nextPageToken")):
            break

    return video_ids


def get_youtube_dl_version() -> str:
    return importlib.metadata.version(yt_dlp.__name__)


def get_ytdlp_options(save_dir: pt.Path, overwrite: bool) -> dict[str, typing.Any]:
    user_agent: str = (
        "Mozilla/5.0 "
        "(Macintosh; Intel Mac OS X 10_15_7)"
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 "
        "Safari/537.36"
    )
    headers: dict[str, str] = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-us,en;q=0.5",
        "Sec-Fetch-Mode": "navigate",
    }
    return {
        "quiet": True,
        "forcejson": True,
        "simulate": False,
        "outtmpl": {
            "default": "%(title)s.%(ext)s",
            "chapter": "%(title)s - %(section_number)03d %(section_title)s [%(id)s].%(ext)s",
        },
        "windowsfilenames": True,
        "paths": {"home": save_dir.absolute().as_posix()},
        "ignoreerrors": "only_download",
        "overwrites": overwrite,
        "continuedl": False,
        "noprogress": True,
        "noplaylist": True,
        "verbose": True,
        "keepvideo": True,
        "postprocessor_args": {"ffmpeg_i1": ["-hwaccel=auto"]},
        "compat_opts": set(),
        "http_headers": headers,
        "nooverwrites": False,
        "forceprint": {},
        "print_to_file": {},
    }


class YouTubeDLPVideoInfo(pydantic.BaseModel):
    video_id: str
    title: str
    quality: str


class YouTubeDLPDownloadResult(pydantic.BaseModel):
    video_id: str
    stdout: str
    stderr: str

    @pydantic.computed_field  # type: ignore[misc]
    @functools.cached_property
    def data(self) -> dict[str, typing.Any]:
        return json.loads(self.stdout.splitlines()[0])

    @pydantic.computed_field  # type: ignore[misc]
    @functools.cached_property
    def file_path(self) -> pt.Path:
        return pt.Path(self.data["filename"])

    @pydantic.computed_field  # type: ignore[misc]
    @functools.cached_property
    def id(self) -> str:
        return self.data["id"]

    @pydantic.computed_field  # type: ignore[misc]
    @functools.cached_property
    def title(self) -> str:
        return self.data["title"]

    @pydantic.computed_field  # type: ignore[misc]
    @functools.cached_property
    def quality(self) -> str:
        return self.data["format"]

    @pydantic.model_validator(mode="after")
    def validate(self) -> typing.Self:
        if not self.file_path.exists():
            raise FileNotFoundError
        return self


def get_video_info(video_id: str) -> YouTubeDLPVideoInfo:
    with yt_dlp.YoutubeDL(get_ytdlp_options(save_dir=pt.Path.cwd(), overwrite=True) | {"simulate": True}) as ydl:
        extracted_info: dict = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
        sanitized_info: dict = ydl.sanitize_info(extracted_info)
        return YouTubeDLPVideoInfo(video_id=video_id, title=sanitized_info["title"], quality=sanitized_info["format"])


def download_video(video_id: str, save_dir: pt.Path, overwrite: bool = True) -> YouTubeDLPDownloadResult:
    with (
        io.StringIO() as stdout,
        io.StringIO() as stderr,
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        with yt_dlp.YoutubeDL(get_ytdlp_options(save_dir=save_dir, overwrite=overwrite)) as ydl:
            if ydl.download([f"https://www.youtube.com/watch?v={video_id}"]) == 0:
                return YouTubeDLPDownloadResult(video_id=video_id, stdout=stdout.getvalue(), stderr=stderr.getvalue())

            logger.error(f"youtube-dlp failed to download video: {video_id}")
            logger.info(f"youtube-dlp stdout:\n{stdout.getvalue()}")
            logger.info(f"youtube-dlp stderr:\n{stderr.getvalue()}")
            raise RuntimeError("youtube-dlp failed")
