import asyncio
import base64
import dataclasses
import io
import json
import logging
import pathlib as pt
import re
import subprocess as sp  # nosec B404
import zlib

import aiohttp
import googleapiclient.discovery as google_api_discovery
import PIL.Image

logger = logging.getLogger(__name__)

VIDEO_REGEX = re.compile(r"(?:youtube\.com|youtu\.be)/(?:[\w-]+\?v=|embed/|v/|shorts/)?([\w-]{11})")
PLAYLIST_REGEX = re.compile(r"(?:youtube\.com|youtu\.be)\/(?:[\w\-\?\&\=\/]+[?&])list=([\w-]{34})")

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


def extract_video_id_from_youtube_url(url: str) -> str | None:
    if match := VIDEO_REGEX.search(url):
        return match.group(1)
    return None


def extract_playlist_id_from_youtube_url(url: str) -> str | None:
    if match := PLAYLIST_REGEX.search(url):
        return match.group(1)
    return None


async def get_thumbnail_img_by_video_id(video_id: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        for qualiy in POSSIBLE_THUMBNAIL_QUALITY:
            link: str = f"https://i.ytimg.com/vi/{video_id}/{qualiy}.jpg"
            async with session.get(link) as response:
                if response.status != 200:
                    continue
                return await response.content.read()

    return THUMBNAIL_BYTES


async def download_thumbnail_img_by_video_id(video_id: str, save_path: pt.Path) -> pt.Path:
    if not save_path.exists():
        save_path.mkdir(parents=True, exist_ok=True)

    PIL.Image.open(io.BytesIO(await get_thumbnail_img_by_video_id(video_id))).save(save_path, format="PNG")
    return save_path


def get_video_ids_from_playlist_id(playlist_id: str, google_api_key: str) -> set[str]:
    youtube_client = google_api_discovery.build("youtube", "v3", developerKey=google_api_key)
    video_ids: set[str] = set()
    page_token: str | None = None

    while True:
        items = (
            youtube_client.playlistItems().list(part="snippet", playlistId=playlist_id, pageToken=page_token).execute()
        )
        video_ids.update(item["snippet"]["resourceId"]["videoId"] for item in items["items"])
        if not (page_token := items.get("nextPageToken")):
            break

    return video_ids


@dataclasses.dataclass
class YoutubeVideoInfo:
    id: str
    title: str
    quality: str


@dataclasses.dataclass
class YoutubeDLPResult(YoutubeVideoInfo):
    stdout: str
    stderr: str
    dumped_json: dict
    file_path: pt.Path


async def get_video_info_from_video_id(executable_info: list[str], video_id: str) -> YoutubeVideoInfo:
    cmdline = [
        *executable_info,
        f"https://www.youtube.com/watch?v={video_id}",
        "-o",
        "%(title)s.%(ext)s",
        "--windows-filenames",
        "--extract-audio",
        "--keep-video",
        "--quiet",
        "--simulate",
        "--skip-download",
        "--print",
        "title",
        "--print",
        "format",
    ]
    process = await asyncio.create_subprocess_exec(*cmdline, stdout=sp.PIPE, stderr=sp.PIPE)
    stdout, _ = map(lambda x: x.decode(), await process.communicate())
    if process.returncode != 0:
        raise RuntimeError(f"youtube-dlp failed - returncode: {process.returncode}")
    if not stdout:
        raise RuntimeError("youtube-dlp failed - no stdout")

    infos: list[str] = list(map(lambda x: x.strip(), stdout.splitlines()))
    return YoutubeVideoInfo(id=video_id, title=infos[0], quality=infos[1])


async def downalod_video_from_video_id(
    executable_info: list[str],
    video_id: str,
    target_path: pt.Path,
    force_overwrite: bool = True,
) -> YoutubeDLPResult:
    if not target_path.exists():
        target_path.mkdir(parents=True, exist_ok=True)

    cmdline: list[str] = [
        *executable_info,
        f"https://www.youtube.com/watch?v={video_id}",
        "--verbose",
        "--dump-json",
        "--no-simulate",
        "--no-update",
        "--no-abort-on-error",
        "--no-continue",
        "--windows-filenames",
        "--postprocessor-args",
        "ffmpeg_i1:-hwaccel=auto",
        "--concat-playlist",
        "never",
        "-P",
        target_path.absolute().as_posix(),
        "-o",
        "%(title)s.%(ext)s",
        "--force-overwrites" if force_overwrite else "--no-force-overwrites",
        "--print",
        "after_move:filepath",
    ]
    process = await asyncio.create_subprocess_exec(*cmdline, stdout=sp.PIPE, stderr=sp.PIPE)
    stdout, stderr = map(lambda x: x.decode(), await process.communicate())
    if process.returncode != 0:
        raise RuntimeError(f"youtube-dlp failed - returncode: {process.returncode}")
    if not stdout:
        raise RuntimeError("youtube-dlp failed - no stdout")

    output = stdout.splitlines()
    if not (file_path := pt.Path(output[-1])).exists():
        raise RuntimeError("youtube-dlp failed - no file")
    dumped_json: dict = json.loads(output[-2])

    return YoutubeDLPResult(
        id=video_id,
        title=dumped_json["title"],
        quality=dumped_json["format"],
        stdout=stdout,
        stderr=stderr,
        dumped_json=dumped_json,
        file_path=file_path,
    )
