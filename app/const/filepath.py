import dataclasses
import pathlib as pt
import uuid


@dataclasses.dataclass(frozen=True)
class FileUploadTo:
    base_path: pt.Path

    @staticmethod
    def mkdir(target_path: pt.Path) -> pt.Path:
        target_path.mkdir(parents=True, exist_ok=True)
        return target_path

    def user_file(self, user_uuid: str | uuid.UUID) -> pt.Path:
        return self.mkdir(self.base_path / "user" / str(user_uuid))

    def youtube_video_dir(self, youtube_vid: str) -> pt.Path:
        return self.mkdir(self.base_path / "youtube" / youtube_vid)

    def youtube_video_thumbnail_file(self, youtube_vid: str) -> pt.Path:
        return self.youtube_video_dir(youtube_vid) / "thumbnail.png"
