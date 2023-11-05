import sqlalchemy as sa
import sqlalchemy.orm as sa_orm

import app.db.__mixin__ as db_mixin
import app.db.__type__ as db_types


class Video(db_mixin.DefaultModelMixin):
    youtube_vid: sa_orm.Mapped[db_types.Str_Unique]
    title: sa_orm.Mapped[db_types.Str]
    data: sa_orm.Mapped[db_types.Json_Nullable]


class VideoUserRelation(db_mixin.DefaultModelMixin):
    __table_args__ = (sa.UniqueConstraint("video_uuid", "user_uuid"),)

    video_uuid: sa_orm.Mapped[db_types.PrimaryKeyType] = sa_orm.mapped_column(
        sa.ForeignKey(Video.uuid), nullable=False, index=True
    )
    user_uuid: sa_orm.Mapped[db_types.UserFK]


class VideoFileRelation(db_mixin.DefaultModelMixin):
    __table_args__ = (sa.UniqueConstraint("video_uuid", "file_uuid"),)

    video_uuid: sa_orm.Mapped[db_types.PrimaryKeyType] = sa_orm.mapped_column(
        sa.ForeignKey(Video.uuid), nullable=False, index=True
    )
    file_uuid: sa_orm.Mapped[db_types.FileFK]


class Playlist(db_mixin.DefaultModelMixin):
    youtube_pid: sa_orm.Mapped[db_types.Str_Nullable]
    title: sa_orm.Mapped[db_types.Str]
    data: sa_orm.Mapped[db_types.Json_Nullable]


class PlaylistUserRelation(db_mixin.DefaultModelMixin):
    __table_args__ = (sa.UniqueConstraint("playlist_uuid", "user_uuid"),)

    playlist_uuid: sa_orm.Mapped[db_types.PrimaryKeyType] = sa_orm.mapped_column(
        sa.ForeignKey(Playlist.uuid), nullable=False, index=True
    )
    user_uuid: sa_orm.Mapped[db_types.UserFK]


class PlaylistVideoRelation(db_mixin.DefaultModelMixin):
    __table_args__ = (sa.UniqueConstraint("playlist_uuid", "index"),)

    playlist_uuid: sa_orm.Mapped[db_types.PrimaryKeyType] = sa_orm.mapped_column(
        sa.ForeignKey(Playlist.uuid), nullable=False, index=True
    )
    video_uuid: sa_orm.Mapped[db_types.PrimaryKeyType] = sa_orm.mapped_column(
        sa.ForeignKey(Video.uuid), nullable=False, index=True
    )
    index: sa_orm.Mapped[int] = sa_orm.mapped_column(sa.Integer, index=True)
