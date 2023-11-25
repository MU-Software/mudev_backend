import typing
import uuid

import sqlalchemy as sa
import typing_extensions as tx

import app.crud.__interface__ as crud_interface
import app.db.__type__ as db_types
import app.db.model.ssco as ssco_model
import app.schema.ssco as ssco_schema


class VideoCRUD(crud_interface.CRUDBase[ssco_model.Video, ssco_schema.VideoCreate, ssco_schema.VideoUpdate]):
    @tx.override
    def update(self, *args: tuple, **kwargs: dict) -> typing.NoReturn:  # type: ignore[override]
        raise NotImplementedError

    @typing.overload
    def get_by_youtube_vid(self, session: db_types.SessionType, youtube_vid: str) -> crud_interface.ModelOrNoneType:
        ...

    @typing.overload
    def get_by_youtube_vid(  # type: ignore[misc]
        self, session: db_types.AsyncSessionType, youtube_vid: str
    ) -> crud_interface.AwaitableModelOrNoneType:
        ...

    def get_by_youtube_vid(
        self, session: db_types.PossibleSessionType, youtube_vid: str
    ) -> crud_interface.PossibleModelOrNoneType:
        return session.scalar(sa.select(ssco_model.Video).where(ssco_model.Video.youtube_vid == youtube_vid))

    def get_by_user_uuid(
        self, session: db_types.SessionType, user_uuid: uuid.UUID
    ) -> sa.ScalarResult[ssco_model.Video]:
        typing.Dict
        return session.scalars(
            sa.select(ssco_model.Video)
            .join(ssco_model.VideoUserRelation)
            .where(ssco_model.VideoUserRelation.user_uuid == user_uuid)
        )

    @typing.overload
    def add_file(self, session: db_types.SessionType, video_uuid: uuid.UUID, file_uuid: uuid.UUID) -> None:
        ...

    @typing.overload
    def add_file(  # type: ignore[misc]
        self, session: db_types.AsyncSessionType, video_uuid: uuid.UUID, file_uuid: uuid.UUID
    ) -> crud_interface.AwaitableNoneType:
        ...

    def add_file(
        self, session: db_types.PossibleSessionType, video_uuid: uuid.UUID, file_uuid: uuid.UUID
    ) -> crud_interface.PossibleNoneType:
        session.add(ssco_model.VideoFileRelation(video_uuid=video_uuid, file_uuid=file_uuid))
        if session._is_asyncio:
            return crud_interface.commit_and_return(session, None)
        return session.commit()


class PlaylistCRUD(crud_interface.CRUDBase[ssco_model.Video, ssco_schema.VideoCreate, ssco_schema.VideoUpdate]):
    @typing.overload
    def add_video(self, session: db_types.SessionType, playlist_uuid: uuid.UUID, video_uuid: uuid.UUID) -> None:
        ...

    @typing.overload
    def add_video(  # type: ignore[misc]
        self, session: db_types.AsyncSessionType, playlist_uuid: uuid.UUID, video_uuid: uuid.UUID
    ) -> crud_interface.AwaitableNoneType:
        ...

    def add_video(
        self, session: db_types.PossibleSessionType, playlist_uuid: uuid.UUID, video_uuid: uuid.UUID
    ) -> crud_interface.PossibleNoneType:
        session.add(ssco_model.PlaylistVideoRelation(playlist_uuid=playlist_uuid, video_uuid=video_uuid))
        if session._is_asyncio:
            return crud_interface.commit_and_return(session, None)
        return session.commit()

    @typing.overload
    def add_user(self, session: db_types.SessionType, playlist_uuid: uuid.UUID, user_uuid: uuid.UUID) -> None:
        ...

    @typing.overload
    def add_user(  # type: ignore[misc]
        self, session: db_types.AsyncSessionType, playlist_uuid: uuid.UUID, user_uuid: uuid.UUID
    ) -> crud_interface.AwaitableNoneType:
        ...

    def add_user(
        self, session: db_types.PossibleSessionType, playlist_uuid: uuid.UUID, user_uuid: uuid.UUID
    ) -> crud_interface.PossibleNoneType:
        session.add(ssco_model.PlaylistUserRelation(playlist_uuid=playlist_uuid, user_uuid=user_uuid))
        if session._is_asyncio:
            return crud_interface.commit_and_return(session, None)
        return session.commit()

    def get_by_user_uuid(
        self, session: db_types.SessionType, user_uuid: uuid.UUID
    ) -> sa.ScalarResult[ssco_model.Playlist]:
        return session.scalars(
            sa.select(ssco_model.Video)
            .join(ssco_model.VideoUserRelation)
            .where(ssco_model.VideoUserRelation.user_uuid == user_uuid)
        )


videoCRUD = VideoCRUD(model=ssco_model.Video)
playlistCRUD = PlaylistCRUD(model=ssco_model.Playlist)
