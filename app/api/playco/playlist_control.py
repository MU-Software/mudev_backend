import flask
import flask.views
import sqlalchemy.exc as sqlexc

import app.common.utils as utils
import app.api.helper_class as api_class
import app.database as db_module
import app.database.jwt as jwt_module
import app.database.playco.playlist as playlist_module
import app.plugin.playco.websocket as playco_ws_module

from app.api.response_case import CommonResponseCase, ResourceResponseCase

db = db_module.db


class PlaylistControlRoute(flask.views.MethodView, api_class.MethodViewMixin):
    @api_class.RequestHeader(auth={api_class.AuthType.Bearer: True, })
    def get(self, playlist_id: int, index: int | None, req_header: dict, access_token: jwt_module.AccessToken):
        '''
        description: Get list of items on playlist. If index is specified, then
        responses:
            - resource_found
            - resource_forbidden
            - resource_not_found
        '''
        if not isinstance(playlist_id, int) or (not playlist_id and playlist_id != 0):
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

        if index:
            try:
                target_playlist_item = target_playlist[int(index)]
                if target_playlist_item:
                    return ResourceResponseCase.resource_found.create_response(
                        header=(('ETag', target_playlist.get_hash()), ),
                        data={'playco_playlist_item': target_playlist_item.to_dict(), }, )
                raise IndexError('target_playlist_item result is None')
            except IndexError:
                return ResourceResponseCase.resource_not_found.create_response(
                    data={'resource_name': 'playco_playlist_item', }, )
            except Exception:
                return CommonResponseCase.server_error.create_response()
        else:
            return ResourceResponseCase.resource_found.create_response(
                header=(('ETag', target_playlist.get_hash()), ),
                data={'playco_playlist': target_playlist.to_dict(
                    include_info=True, include_items=True), }, )

    @api_class.RequestHeader(
        required_fields={'If-Match': {'type': 'string', }, },
        auth={api_class.AuthType.Bearer: True, })
    @api_class.RequestBody(
        required_fields={'link': {'type': 'string', }, },
        optional_fields={'index': {'type': 'integer', }, }, )
    def post(self,
             playlist_id: int,
             index: None,
             req_header: dict,
             req_body: dict,
             access_token: jwt_module.AccessToken):
        '''
        description: Insert new link on playlist
        responses:
            - resource_modified
            - resource_forbidden
            - resource_prediction_failed
            - resource_unique_failed
            - resource_not_found
            - db_error
            - server_error
        '''
        if (not isinstance(playlist_id, int) or (not playlist_id and playlist_id != 0)) or index:
            return CommonResponseCase.http_mtd_forbidden.create_response()

        target_playlist = db.session.query(playlist_module.Playlist)\
            .filter(playlist_module.Playlist.uuid == playlist_id)\
            .first()
        if not target_playlist:
            return ResourceResponseCase.resource_not_found.create_response(
                data={'resource_name': 'playco_playlist', }, )
        elif not target_playlist.public_item_appendable and target_playlist.user_id != access_token.user:
            # Send 404 response so that another user cannot detect this private resource available
            return ResourceResponseCase.resource_not_found.create_response(
                data={'resource_name': 'playco_playlist', }, )
        elif target_playlist.blocked_at:
            err_msg = 'This playlist is blocked. '\
                + f'when: {target_playlist.blocked_at},'\
                + f'reason: {target_playlist.why_blocked} '
            return ResourceResponseCase.resource_forbidden.create_response(
                message=err_msg, data=target_playlist.to_json(), )
        elif target_playlist.get_hash() != req_header.get('If-Match', ''):  # We need to check full hash
            # Check hash so that mis-sync issue does not occur.
            return ResourceResponseCase.resource_prediction_failed.create_response(
                message='Playlist data that client holds seems to be old. Re-sync the data again.',
                data={'prediction_failed_reason': ['playlist_outdated', ]})

        try:
            target_playlist.insert(
                index=req_body.get('index', -1),
                link=req_body.get('link', ''),
                added_by_id=access_token.user,
                commit=True)
        except NotImplementedError as err:
            db.session.rollback()

            errMsg, prediction_failed_reason = '', ''
            if str(err).startswith('NotSupported'):
                errMsg = 'Currently, only YouTube link is supported.'
                prediction_failed_reason = 'link_not_implemented'
            elif str(err).startswith('DataLoadFailed'):
                errMsg = 'We failed to get data from requested link.'
                prediction_failed_reason = 'link_data_fetch_failed'
            else:
                errMsg = 'Unknown error raised while identifying requested link'
                prediction_failed_reason = 'link_identify_failed'

            return ResourceResponseCase.resource_prediction_failed.create_response(
                message=errMsg, data={'prediction_failed_reason': [prediction_failed_reason, ]})
        except sqlexc.SQLAlchemyError as err:
            raise err
        except Exception as err:
            db.session.rollback()
            if str(err).split(':')[0] == 'AlreadyIncluded':
                return ResourceResponseCase.resource_unique_failed.create_response(
                    message='This playlist cannot add the same link again, '
                    'this means that the link you requested already been added to this playlist. '
                    'If you want to add the link in this playlist again, '
                    'please enable \'allow_duplicate\' in playlist setting.')

            raise err

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
            data={'playco_playlist': target_playlist.to_dict(include_info=True, include_items=True), }, )

    # TODO: Implement this!
    # @api_class.RequestHeader(auth={api_class.AuthType.Bearer: True, })
    # def put(self, playlist_id: int, index: None, req_header: dict, access_token: jwt_module.AccessToken):
    #     '''
    #     description: Set whole playlist by uploading whole new representation
    #     responses:
    #         - multiple_resources_found
    #         - resource_not_found
    #     '''

    @api_class.RequestHeader(
        required_fields={'If-Match': {'type': 'string', }, },
        auth={api_class.AuthType.Bearer: True, })
    @api_class.RequestBody(required_fields={'link': {'type': 'string', }, }, )
    def patch(self,
              playlist_id: int,
              index: int,
              req_header: dict,
              req_body: dict,
              access_token: jwt_module.AccessToken):
        '''
        description: Move specific link to index on path.
        responses:
            - resource_modified
            - resource_forbidden
            - resource_not_found
            - db_error
            - server_error
        '''
        if (not isinstance(playlist_id, int) or (not playlist_id and playlist_id != 0)) or not index:
            return CommonResponseCase.http_mtd_forbidden.create_response()

        target_playlist = db.session.query(playlist_module.Playlist)\
            .filter(playlist_module.Playlist.uuid == playlist_id)\
            .first()
        if not target_playlist:
            return ResourceResponseCase.resource_not_found.create_response(
                data={'resource_name': 'playco_playlist', }, )
        elif not target_playlist.public_item_orderable and target_playlist.user_id != access_token.user:
            # Send 404 response so that another user cannot detect this private resource available
            return ResourceResponseCase.resource_not_found.create_response(
                data={'resource_name': 'playco_playlist', }, )
        elif target_playlist.blocked_at:
            err_msg = 'This playlist is blocked. '\
                + f'when: {target_playlist.blocked_at},'\
                + f'reason: {target_playlist.why_blocked} '
            return ResourceResponseCase.resource_forbidden.create_response(
                message=err_msg, data=target_playlist.to_json(), )
        elif target_playlist.get_hash() != req_header.get('If-Match', ''):  # We need to check full hash
            # Check hash so that mis-sync issue does not occur.
            return ResourceResponseCase.resource_prediction_failed.create_response(
                message='Playlist data that client holds seems to be old. Re-sync the data again.',
                data={'prediction_failed_reason': ['playlist_outdated', ]})

        target_link = req_body.get('link', '')
        item_on_current_index = target_playlist[index]
        if not target_link:
            return CommonResponseCase.body_bad_semantics.create_response()
        elif item_on_current_index.link == target_link:
            return ResourceResponseCase.resource_conflict.create_response(
                message='Item already on position')

        target_playlist_item: playlist_module.PlaylistItem = target_playlist.get_by_link(req_body.get('link', ''))
        if not target_playlist_item:
            return ResourceResponseCase.resource_not_found.create_response(
                data={'resource_name': 'playco_playlist_item'}, )
        try:
            db.session.delete(target_playlist_item)
            target_playlist.insert(index, target_link, access_token.user)
        except NotImplementedError:
            db.session.rollback()
            return ResourceResponseCase.resource_prediction_failed.create_response(
                message='Currently, only YouTube link is supported.',
                data={'prediction_failed_reason': ['link_not_implemented', ]})
        except sqlexc.SQLAlchemyError:
            db.session.rollback()
            return CommonResponseCase.db_error.create_response()
        except Exception as err:
            db.session.rollback()
            if str(err).split(':')[0] == 'AlreadyIncluded':
                return ResourceResponseCase.resource_unique_failed.create_response(
                    message='This playlist cannot add the same link again, '
                    'this means that the link you requested already been added to this playlist. '
                    'If you want to add the link in this playlist again, '
                    'please enable \'allow_duplicate\' in playlist setting.')

        # FIXME: TODO: Need to change currently_playing_index on redis room when item indexes are changed.

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
                include_info=True, include_items=True), }, )

    @api_class.RequestHeader(
        required_fields={'If-Match': {'type': 'string', }, },
        auth={api_class.AuthType.Bearer: True, })
    def delete(self, playlist_id: int, index: int, req_header: dict, access_token: jwt_module.AccessToken):
        '''
        description: Delete item on playlist
        responses:
            - resource_deleted
            - resource_forbidden
            - resource_not_found
            - db_error
            - server_error
        '''
        if (not isinstance(playlist_id, int) or (not playlist_id and playlist_id != 0))\
           or (not isinstance(index, int) or (not index and index != 0)):
            return CommonResponseCase.http_mtd_forbidden.create_response()

        target_playlist = db.session.query(playlist_module.Playlist)\
            .filter(playlist_module.Playlist.uuid == playlist_id)\
            .first()
        if not target_playlist:
            return ResourceResponseCase.resource_not_found.create_response(
                data={'resource_name': 'playco_playlist', }, )
        elif not target_playlist.public_item_deletable and target_playlist.user_id != access_token.user:
            # Send 404 response so that another user cannot detect this private resource available
            return ResourceResponseCase.resource_not_found.create_response(
                data={'resource_name': 'playco_playlist', }, )
        elif target_playlist.blocked_at:
            err_msg = 'This playlist is blocked. '\
                + f'when: {target_playlist.blocked_at},'\
                + f'reason: {target_playlist.why_blocked} '
            return ResourceResponseCase.resource_forbidden.create_response(
                message=err_msg, data=target_playlist.to_json(), )
        elif target_playlist.get_hash() != req_header.get('If-Match', ''):  # We need to check full hash
            # Check hash so that mis-sync issue does not occur.
            return ResourceResponseCase.resource_prediction_failed.create_response(
                message='Playlist data that client holds seems to be old. Re-sync the data again.',
                data={'prediction_failed_reason': ['playlist_outdated', ]})

        try:
            del target_playlist[int(index)]

            try:
                playco_ws = playco_ws_module.PlayCoWebsocket()

                if not (target_room := playco_ws.redis_mgr.get_room(target_playlist.uuid)):
                    # No room for playlist exists
                    raise KeyError

                # We need to find whom to modify current_playing.
                room_stat_collection = [
                    (sid, stat['status']['currently_playing']) for sid, stat in target_room['sid'].items()
                ]
                # We need to subtract the currently playing index value of the sessions
                # in deleted items and subsequent items,
                # but subtracted result must be at least 0.
                target_sid_to_mod = [sid for sid, idx in room_stat_collection if idx >= int(index) and idx != 0]

                for target_sid in target_sid_to_mod:
                    target_room['sid'][target_sid]['status']['currently_playing'] -= 1
                    if target_room['sid'][target_sid]['status']['currently_playing'] < 0:
                        target_room['sid'][target_sid]['status']['currently_playing'] = 0

                # Commit to redis.
                playco_ws.redis_mgr.set_room(target_playlist.uuid, target_room)

                # Broadcast new status to all room participants.
                playco_ws.event_handler.broadcast_updated_status_on_room(target_playlist.uuid)
            except KeyError:
                # No room for playlist exist, ignore this.
                pass
            except Exception as err:
                print(utils.get_traceback_msg(err), flush=True)

            return ResourceResponseCase.resource_deleted.create_response()
        except IndexError:
            return ResourceResponseCase.resource_not_found.create_response(
                data={'resource_name': 'playco_playlist_item', }, )
        except sqlexc.SQLAlchemyError as err:
            raise err
        except Exception as err:
            raise err
