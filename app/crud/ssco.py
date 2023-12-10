import app.crud.__interface__ as crud_interface
import app.db.model.ssco as ssco_model
import app.schema.ssco as ssco_schema

videoCRUD = crud_interface.CRUDBase[
    ssco_model.Video,
    ssco_schema.VideoCreate,
    ssco_schema.VideoUpdate,
](model=ssco_model.Video)
playlistCRUD = crud_interface.CRUDBase[
    ssco_model.Playlist,
    ssco_schema.PlaylistCreate,
    ssco_schema.PlaylistUpdate,
](model=ssco_model.Playlist)
