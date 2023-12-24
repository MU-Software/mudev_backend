import dataclasses
import pathlib as pt
import uuid

import app.util.time_util as time_util


@dataclasses.dataclass(frozen=True)
class FileUploadTo:
    base_path: pt.Path

    @staticmethod
    def assure_dir(target_path: pt.Path) -> pt.Path:
        target_path.mkdir(parents=True, exist_ok=True)
        return target_path

    @property
    def current_timestamp(self) -> int:
        return int(time_util.get_utcnow().timestamp())

    def user_file(self, user_uuid: uuid.UUID, file_name: str) -> pt.Path:
        return self.assure_dir(self.base_path / "user" / str(user_uuid)) / file_name

    def youtube_video_dir(self, youtube_vid: str) -> pt.Path:
        return self.assure_dir(self.base_path / "youtube" / youtube_vid)

    def youtube_video_thumbnail_file(self, youtube_vid: str) -> pt.Path:
        return self.youtube_video_dir(youtube_vid) / "thumbnail.png"
