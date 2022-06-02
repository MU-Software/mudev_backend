import flask
import flask.views
import json

import app.common.utils as utils
import app.api.helper_class as api_class
import app.database as db_module
import app.database.jwt as jwt_module
import app.database.playco.playlist as playlist_module
import app.plugin.playco.websocket as playco_ws_module

from app.api.response_case import CommonResponseCase, ResourceResponseCase

db = db_module.db

CREATABLE_USER_PLAYLIST_MAXIMUM_COUNT = 5


class PlaylistManagementRoute(flask.views.MethodView, api_class.MethodViewMixin):
    @api_class.RequestHeader(auth={api_class.AuthType.Bearer: True, })
    def head(self, playlist_id: int, req_header: dict, access_token: jwt_module.AccessToken):
        '''
        description: Get playlist information hash. Notes that this 'includes' the list item informations
        responses:
            - resource_found
            - resource_forbidden
            - resource_not_found
        '''
        if not playlist_id:
            return CommonResponseCase.http_mtd_forbidden.create_response()

        target_playlist = db.session.query(playlist_module.Playlist)\
            .filter(playlist_module.Playlist.uuid == playlist_id)\
            .first()
        if not target_playlist:
            return ResourceResponseCase.resource_not_found.create_response(
                data={'resource_name': 'playco_playlist', }, )
        elif not target_playlist.public_accessable and target_playlist.user_id != access_token.user:
            # Send 404 response so that another user cannot detect this private resource available
            return ResourceResponseCase.resource_not_found.create_response(
                data={'resource_name': 'playco_playlist', }, )
        elif target_playlist.blocked_at:
            err_msg = 'This playlist is blocked. '\
                + f'when: {target_playlist.blocked_at},'\
                + f'reason: {target_playlist.why_blocked} '
            return ResourceResponseCase.resource_forbidden.create_response(
                message=err_msg, data=target_playlist.to_json(), )

        return ResourceResponseCase.resource_found.create_response(
            header=(('ETag', target_playlist.get_hash()), ))

    @api_class.RequestHeader(auth={api_class.AuthType.Bearer: True, })
    def get(self, playlist_id: int | None, req_header: dict, access_token: jwt_module.AccessToken):
        '''
        description: Get my playlists if playlist_id is not given,
            and get playlist information if playlist_id is given.
            Notes that this does not include the list items
        responses:
            - resource_found
            - multiple_resources_found
            - resource_forbidden
            - resource_not_found
        '''
        if not playlist_id:
            target_playlists = db.session.query(playlist_module.Playlist)\
                .filter(playlist_module.Playlist.user_id == access_token.user)\
                .all()
            if not target_playlists:
                return ResourceResponseCase.resource_not_found.create_response(
                    data={'resource_name': 'playco_playlist', }, )

            playlist_infos = [
                playlist.to_dict(
                    include_info=True,
                    include_items=False,
                    include_count=True,
                    include_hash=False)
                for playlist in target_playlists]

            try:
                # Add participant count if possible
                playlist_ids: list[int] = [z['uuid'] for z in playlist_infos]
                playco_ws = playco_ws_module.PlayCoWebsocket()
                playlist_participant_counts = playco_ws.redis_mgr.get_room_participants_number(playlist_ids) or dict()

                for playlist_info in playlist_infos:
                    playlist_id = playlist_info['uuid']
                    if playlist_id in playlist_participant_counts:
                        playlist_info['participant_count'] = playlist_participant_counts.get(playlist_id, 0)
            except Exception as err_sub_1:
                print(utils.get_traceback_msg(err_sub_1), flush=True)

            return ResourceResponseCase.multiple_resources_found.create_response(
                data={'playco_playlists': playlist_infos, }, )

        target_playlist = db.session.query(playlist_module.Playlist)\
            .filter(playlist_module.Playlist.uuid == playlist_id)\
            .first()
        if not target_playlist:
            return ResourceResponseCase.resource_not_found.create_response(
                data={'resource_name': 'playco_playlist', }, )
        elif not target_playlist.public_accessable and target_playlist.user_id != access_token.user:
            # Send 404 response so that another user cannot detect this private resource available
            return ResourceResponseCase.resource_not_found.create_response(
                data={'resource_name': 'playco_playlist', }, )
        elif target_playlist.blocked_at:
            err_msg = 'This playlist is blocked. '\
                + f'when: {target_playlist.blocked_at},'\
                + f'reason: {target_playlist.why_blocked} '
            return ResourceResponseCase.resource_forbidden.create_response(
                message=err_msg, data=target_playlist.to_json(), )

        return ResourceResponseCase.resource_found.create_response(
            header=(('ETag', target_playlist.get_hash()), ),
            data={'playco_playlist': target_playlist.to_dict(
                include_info=True, include_items=False), }, )

    @api_class.RequestHeader(auth={api_class.AuthType.Bearer: True, })
    @api_class.RequestBody(
        required_fields={'name': {'type': 'string', }, },
        optional_fields={
            'description': {'type': 'string', },
            'allow_duplicate': {'type': 'boolean', },
            'public_accessable': {'type': 'boolean', },
            'public_item_appendable': {'type': 'boolean', },
            'public_item_orderable': {'type': 'boolean', },
            'public_item_deletable': {'type': 'boolean', }, }, )
    def post(self, playlist_id: None, req_header: dict, req_body: dict, access_token: jwt_module.AccessToken):
        '''
        description: Create new playlist.
            If user has playlists more than CREATABLE_USER_PLAYLIST_MAXIMUM_COUNT,
            then resource_unique_failed will be returned.
        responses:
            - resource_created
            - resource_unique_failed
            - server_error
        '''
        if playlist_id:
            return CommonResponseCase.http_mtd_forbidden.create_response()

        # Set user playlist creation limit.
        user_last_playlists = db.session.query(playlist_module.Playlist)\
            .filter(playlist_module.Playlist.user_id == access_token.user)\
            .all()
        if len(user_last_playlists) >= CREATABLE_USER_PLAYLIST_MAXIMUM_COUNT:
            return ResourceResponseCase.resource_unique_failed.create_response(
                message=f'You can\'t create more than {CREATABLE_USER_PLAYLIST_MAXIMUM_COUNT} playlists.', )

        target_playlist = playlist_module.Playlist()
        target_playlist.user_id = access_token.user
        target_playlist.index = 0 if not user_last_playlists else user_last_playlists[0].index + 1
        target_playlist.config_json = json.dumps({})

        target_column = [
            'name', 'description', 'allow_duplicate', 'public_accessable',
            'public_item_appendable', 'public_item_orderable', 'public_item_deletable', ]
        for column in target_column:
            if column in req_body:
                setattr(target_playlist, column, req_body.get(column))

        db.session.add(target_playlist)
        db.session.commit()
        return ResourceResponseCase.resource_created.create_response(
            header=(('ETag', target_playlist.get_hash()), ),
            data={'playco_playlist': target_playlist.to_dict(include_info=True, include_items=False), }, )

    @api_class.RequestHeader(
        required_fields={'If-Match': {'type': 'string', }, },
        auth={api_class.AuthType.Bearer: True, }, )
    @api_class.RequestBody(
        optional_fields={
            'name': {'type': 'string', },
            'description': {'type': 'string', },
            'allow_duplicate': {'type': 'boolean', },
            'public_accessable': {'type': 'boolean', },
            'public_item_appendable': {'type': 'boolean', },
            'public_item_orderable': {'type': 'boolean', },
            'public_item_deletable': {'type': 'boolean', }, }, )
    def patch(self, playlist_id: int, req_header: dict, req_body: dict, access_token: jwt_module.AccessToken):
        '''
        description: Modify playlist information
        responses:
            - resource_modified
            - resource_forbidden
            - resource_not_found
        '''
        if not playlist_id:
            return CommonResponseCase.http_mtd_forbidden.create_response()

        target_playlist = db.session.query(playlist_module.Playlist)\
            .filter(playlist_module.Playlist.uuid == playlist_id)\
            .first()
        if not target_playlist:
            return ResourceResponseCase.resource_not_found.create_response(
                data={'resource_name': 'playco_playlist', }, )
        elif not target_playlist.public_modifiable and target_playlist.user_id != access_token.user:
            # Send 404 response so that another user cannot detect this private resource available
            return ResourceResponseCase.resource_not_found.create_response(
                data={'resource_name': 'playco_playlist', }, )
        elif target_playlist.blocked_at:
            err_msg = 'This playlist is blocked. '\
                + f'when: {target_playlist.blocked_at},'\
                + f'reason: {target_playlist.why_blocked} '
            return ResourceResponseCase.resource_forbidden.create_response(
                message=err_msg, data=target_playlist.to_json(), )
        elif target_playlist.commit_id != req_header.get('If-Match', '').split(':')[0]:
            # Check commit_id so that mis-sync issue does not occur.
            return ResourceResponseCase.resource_prediction_failed.create_response(
                message='Playlist data that client holds seems to be old. Re-sync the data again.',
                data={'prediction_failed_reason': ['playlist_outdated', ]})
        target_column = [
            'name', 'description', 'allow_duplicate', 'public_accessable',
            'public_item_appendable', 'public_item_orderable', 'public_item_deletable', ]
        for column in target_column:
            if column in req_body:
                setattr(target_playlist, column, req_body.get(column))

        db.session.commit()

        try:
            playco_ws = playco_ws_module.PlayCoWebsocket()
            playco_ws.event_handler.broadcast_updated_status_on_room(target_playlist.uuid)
        except KeyError:
            # No room for playlist exist, ignore this.
            pass
        except Exception as err:
            print(utils.get_traceback_msg(err), flush=True)

        return ResourceResponseCase.resource_modified.create_response(
            header=(('ETag', target_playlist.get_hash()), ),
            data={'playco_playlist': target_playlist.to_dict(
                include_info=True, include_items=False), }, )

    @api_class.RequestHeader(auth={api_class.AuthType.Bearer: True, })
    def delete(self, playlist_id: int, req_header: dict, access_token: jwt_module.AccessToken):
        '''
        description: Delete playlist
        responses:
            - resource_deleted
            - resource_forbidden
            - resource_not_found
        '''
        if not playlist_id:
            return CommonResponseCase.http_mtd_forbidden.create_response()

        target_playlist = db.session.query(playlist_module.Playlist)\
            .filter(playlist_module.Playlist.uuid == playlist_id)\
            .first()
        if not target_playlist:
            return ResourceResponseCase.resource_not_found.create_response(
                data={'resource_name': 'playco_playlist', }, )
        elif target_playlist.user_id != access_token.user:
            # Send 404 response so that another user cannot detect this private resource available
            return ResourceResponseCase.resource_not_found.create_response(
                data={'resource_name': 'playco_playlist', }, )
        elif target_playlist.blocked_at:
            err_msg = 'This playlist is blocked. '\
                + f'when: {target_playlist.blocked_at},'\
                + f'reason: {target_playlist.why_blocked} '
            return ResourceResponseCase.resource_forbidden.create_response(
                message=err_msg, data=target_playlist.to_json(), )

        try:
            # Get participant count.
            # If there's a participant in this room, then user cannot delete this room.
            playco_ws = playco_ws_module.PlayCoWebsocket()
            playlist_participant_count = playco_ws.redis_mgr.get_room_participant_number(playlist_id)

            if playlist_participant_count:
                return ResourceResponseCase.resource_conflict.create_response(
                    message='The user exists in the room you want to delete.',
                    data={'conflict_reason': ['participant_exists_in_delete_target_room', ]}, )
        except Exception as err_sub_1:
            print(utils.get_traceback_msg(err_sub_1), flush=True)

        db.session.delete(target_playlist)
        db.session.commit()

        return ResourceResponseCase.resource_deleted.create_response()
