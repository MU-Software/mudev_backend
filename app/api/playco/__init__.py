# (c) MUsoftware, 2021, MIT License
# OK, we need to build those APIs on this service
# - CRUD youtube link to playlist
#   - Get list of links of playlist
#   - Insert / Pop links to playlist
#   - Update the order of the playlist
#   - Get hash of list of links of playlist
# - Add settings to playlist
#   - loop option
#   - delete/preserve/send to last when video played
# - Provide Websocket so that user can get realtime event
#   - (like insert/pop/modify)
import app.api.playco.playlist_manage as route_playlist_mgr
import app.api.playco.playlist_control as route_playlist_ctl
import app.api.playco.socketio_auth as route_socketio_auth

playco_resource_route = {
    '/playco/playlists/<int:playlist_id>': {
        'view_func': route_playlist_mgr.PlaylistManagementRoute,
        'base_path': '/playco/playlists/',
        'defaults': {'playlist_id': None, },
    },
    '/playco/playlists/<int:playlist_id>/items/<int:index>': {
        'view_func': route_playlist_ctl.PlaylistControlRoute,
        'base_path': '/playco/playlists/<int:playlist_id>/items',
        'defaults': {'index': None, },
    },
    '/playco/socketio/auth': route_socketio_auth.PlayCoSocketIOAuthRoute,
}
