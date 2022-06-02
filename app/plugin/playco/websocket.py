import enum
import flask
import flask_socketio
import jwt.exceptions as pyjwt_exc

import app.common.utils as utils
import app.database as db_module

import app.plugin.playco.redis_db as playco_redis

db = db_module.db


class PlayCoWebsocket(metaclass=utils.Singleton):
    namespace = '/playco_ws'
    redis_mgr = playco_redis.PlayCoRedis()
    event_handler: 'EventHandler' = None
    socketio_app: flask_socketio.SocketIO = None

    @classmethod
    def gen(cls):
        if not cls.event_handler:
            cls.event_handler = cls.EventHandler(cls.namespace)
        return cls.event_handler

    @classmethod
    def register_on_app(cls, app: flask_socketio.SocketIO):
        cls.socketio_app = app
        cls.socketio_app.on_namespace(cls.gen())

    class EventHandler(flask_socketio.Namespace):
        class ResponseEventType(utils.EnumAutoName):
            REQUEST_RESPONSE = enum.auto()
            PLAYLIST_USER_ENTERED = enum.auto()
            PLAYLIST_USER_EXITED = enum.auto()
            PLAYLIST_MODIFIED = enum.auto()
            OFFICIAL_ANNOUNCEMENT = enum.auto()

        class CommonSocketIOPayload:
            # 200
            ROOM_MODIFIED = {
                'code': 200,
                'subCode': 'ROOM_MODIFIED',
                'success': True,
                'message': '방의 데이터가 수정됐습니다.',
                'data': {}
            }
            USER_JOINED = {
                'code': 200,
                'subCode': 'USER_JOINED',
                'success': True,
                'message': '방에 입장했습니다.',
                'data': {}
            }
            USER_LEFT_SELF = {
                'code': 200,
                'subCode': 'USER_LEFT_SELF',
                'success': True,
                'message': '방에서 퇴장했습니다.'
            }

            # 201
            SESSION_CREATED = {
                'code': 201,
                'subCode': 'SESSION_CREATED',
                'success': True,
                'message': '세션을 정상적으로 생성했습니다.',
                'data': {}
            }

            # 204
            ROOM_CLOSED = {
                'code': 204,
                'subCode': 'ROOM_CLOSED',
                'success': True,
                'message': '마지막 인원이 떠나 방이 닫혔습니다.',
            }

            # 400
            SESSION_ALREADY_CREATED = {
                'code': 400,
                'subCode': 'SESSION_ALREADY_CREATED',
                'success': False,
                'message': '이미 세션이 존재합니다, 10분 후 다시 시도해주세요.'
            }
            MAX_SESSION_CONNECTED = {
                'code': 400,
                'subCode': 'MAX_SESSION_CONNECTED',
                'success': False,
                'message': '이미 많은 세션이 접속 중입니다, 10분 후 다시 시도해주세요.'
            }
            PAYLOAD_REQUIRED_OMITTED = {
                'code': 400,
                'subCode': 'PAYLOAD_REQUIRED_OMITTED',
                'success': False,
                'message': '필요한 정보가 요청에 포함되지 않았어요, 개발자에게 문의해주세요.'
            }
            SIO_TOKEN_EXPIRED = {
                'code': 400,
                'subCode': 'SIO_TOKEN_EXPIRED',
                'success': False,
                'message': '세션 토큰이 너무 오래되었습니다, 다시 접속해주세요.'
            }
            SIO_TOKEN_INVALID = {
                'code': 400,
                'subCode': 'SIO_TOKEN_INVALID',
                'success': False,
                'message': '세션 토큰이 유효하지 않습니다, 다시 접속해주세요.'
            }

            # 404
            USER_NOT_EXIST = {
                'code': 404,
                'subCode': 'USER_NOT_EXIST',
                'success': False,
                'message': '사용자가 존재하지 않습니다, 다시 로그인해주세요.'
            }
            SESSION_NOT_EXIST = {
                'code': 404,
                'subCode': 'SESSION_NOT_EXIST',
                'success': False,
                'message': '세션이 존재하지 않습니다, 다시 접속해주세요.'
            }
            ROOM_NOT_EXIST = {
                'code': 404,
                'subCode': 'ROOM_NOT_EXIST',
                'success': False,
                'message': '방이 존재하지 않습니다.'
            }
            PLAYLIST_NOT_EXIST = {
                'code': 404,
                'subCode': 'PLAYLIST_NOT_EXIST',
                'success': False,
                'message': '재생목록이 존재하지 않습니다.'
            }

            # 500
            SERVER_ERROR = {
                'code': 500,
                'subCode': 'SERVER_ERROR',
                'success': False,
                'message': '알 수 없는 오류가 발생했습니다.'
            }

        # Event handler function
        def on_connect(self, **kwargs):
            # We don't do anything on here.
            pass

        # Event handler function
        def on_disconnect(self, **kwargs):
            try:
                sid = flask.request.sid
                # We need to leave room here as we need to broadcast to room where disconnected user left.
                target_session_rec = PlayCoWebsocket.redis_mgr.get_session(sid)
                if not target_session_rec:
                    return

                for pid in target_session_rec['entered_room']:
                    try:
                        if room_data := PlayCoWebsocket.redis_mgr.exit_room(pid, sid, '', '', True):
                            self.broadcast_on_room(
                                pid=pid, event=self.ResponseEventType.PLAYLIST_USER_EXITED.value,
                                data=self.CommonSocketIOPayload.USER_LEFT_SELF | {
                                    'data': {'room': PlayCoWebsocket.redis_mgr.room_publicify(room_data), }
                                },
                                send_to_requester=True)
                            flask_socketio.leave_room(room=pid, sid=sid, namespace=PlayCoWebsocket.namespace)
                        else:
                            flask_socketio.close_room(room=pid, namespace=PlayCoWebsocket.namespace)
                    except Exception as err1:
                        print(utils.get_traceback_msg(err1), flush=True)

                PlayCoWebsocket.redis_mgr.destroy_session(sid=sid)
            except Exception as err:  # Unknown exception raised, like RedisCommitFailure.
                print(utils.get_traceback_msg(err), flush=True)

        # Event handler function
        def on_playco_connect(self, data=None):
            data = data or dict()
            try:
                sid = flask.request.sid
                if not (request_id := data.get('request_id', None)):
                    self.response(
                        0,
                        self.CommonSocketIOPayload.PAYLOAD_REQUIRED_OMITTED | {'data': {'omitted': 'request_id'}})
                    return
                if not (sio_token_str := data.get('sio_token', None)):
                    self.response(
                        request_id,
                        self.CommonSocketIOPayload.PAYLOAD_REQUIRED_OMITTED | {'data': {'omitted': 'sio_token'}})
                    return
                if not (sio_csrf_token_str := data.get('sio_csrf_token', None)):
                    self.response(
                        request_id,
                        self.CommonSocketIOPayload.PAYLOAD_REQUIRED_OMITTED | {'data': {'omitted': 'sio_csrf_token'}})
                    return

                PlayCoWebsocket.redis_mgr.create_session(
                    sid=sid,
                    sio_token_str=sio_token_str,
                    sio_csrf_token_str=sio_csrf_token_str)
                self.response(request_id, self.CommonSocketIOPayload.SESSION_CREATED)

            except pyjwt_exc.ExpiredSignatureError:  # Token is too old!
                self.response(request_id, self.CommonSocketIOPayload.SIO_TOKEN_EXPIRED)
            except pyjwt_exc.PyJWTError:  # Token is invalid!
                self.response(request_id, self.CommonSocketIOPayload.SIO_TOKEN_INVALID)
            except KeyError as err:  # 'User not found' or 'Session already exists'!
                if str(err).startswith('User'):  # User not found
                    self.response(request_id, self.CommonSocketIOPayload.USER_NOT_EXIST)
                else:  # Session already exists
                    self.response(request_id, self.CommonSocketIOPayload.SESSION_ALREADY_CREATED)
            except OverflowError:  # User has more than MAX_CONNECTIONS_PER_USER already.
                self.response(request_id, self.CommonSocketIOPayload.MAX_SESSION_CONNECTED)
                self.disconnect(sid)
            except Exception as err:  # Unknown exception raised, like RedisCommitFailure.
                print(utils.get_traceback_msg(err), flush=True)
                self.response(request_id, self.CommonSocketIOPayload.SERVER_ERROR)

        # Event handler function
        def on_playlist_enter(self, data=None):
            data = data or dict()
            try:
                sid = flask.request.sid
                if not (request_id := data.get('request_id', None)):
                    self.response(
                        0,
                        self.CommonSocketIOPayload.PAYLOAD_REQUIRED_OMITTED | {'data': {'omitted': 'request_id'}})
                    return
                if not (sio_token_str := data.get('sio_token', None)):
                    self.response(
                        request_id,
                        self.CommonSocketIOPayload.PAYLOAD_REQUIRED_OMITTED | {'data': {'omitted': 'sio_token'}})
                    return
                if not (sio_csrf_token_str := data.get('sio_csrf_token', None)):
                    self.response(
                        request_id,
                        self.CommonSocketIOPayload.PAYLOAD_REQUIRED_OMITTED | {'data': {'omitted': 'sio_csrf_token'}})
                    return
                if not (pid := utils.safe_int(data.get('playlist_id', None))):
                    self.response(
                        request_id,
                        self.CommonSocketIOPayload.PAYLOAD_REQUIRED_OMITTED | {'data': {'omitted': 'playlist_id'}})
                    return

                # utils.safe_int returns 0, and 0 is a valid index, but it's false.
                safe_int_none = utils.ignore_exception(Exception, None)(int)
                currently_playing: int | None = safe_int_none(data.get('currently_playing', None))
                # currently_playing can be a null, as this is optional.

                room_data = PlayCoWebsocket.redis_mgr.enter_room(pid, sid, sio_token_str, sio_csrf_token_str)
                flask_socketio.join_room(room=pid, sid=sid, namespace=PlayCoWebsocket.namespace)

                if currently_playing is not None:
                    # We need to send room status after setting session status.

                    if not (target_room_sid := room_data.get('sid', {}).get(sid)):
                        self.response(request_id, self.CommonSocketIOPayload.SESSION_NOT_EXIST)
                        return

                    # Update session status
                    session_status = target_room_sid['status']
                    session_status['currently_playing'] = currently_playing

                    # Commit to redis
                    PlayCoWebsocket.redis_mgr.update_session_status_on_room(
                        pid, sid, sio_token_str, sio_csrf_token_str, session_status)

                self.broadcast_on_room(
                    pid=pid,
                    event=self.ResponseEventType.PLAYLIST_USER_ENTERED.value,
                    data=self.CommonSocketIOPayload.USER_JOINED | {
                        'data': {'room': PlayCoWebsocket.redis_mgr.room_publicify(room_data), }
                    },
                    send_to_requester=True)
                self.response(request_id, self.CommonSocketIOPayload.USER_JOINED)

            except pyjwt_exc.ExpiredSignatureError:  # Token is too old!
                self.response(request_id, self.CommonSocketIOPayload.SIO_TOKEN_EXPIRED)
            except pyjwt_exc.PyJWTError:  # Token is invalid!
                self.response(request_id, self.CommonSocketIOPayload.SIO_TOKEN_INVALID)
            except KeyError:  # Session does not exist, disconnect this client!
                self.response(request_id, self.CommonSocketIOPayload.SESSION_NOT_EXIST)
                self.disconnect(sid)
            except ValueError:  # Playlist does not exist
                self.response(request_id, self.CommonSocketIOPayload.PLAYLIST_NOT_EXIST)
            except Exception as err:  # Unknown exception raised, like RedisCommitFailure.
                print(utils.get_traceback_msg(err), flush=True)
                self.response(request_id, self.CommonSocketIOPayload.SERVER_ERROR)

        # Event handler function
        def on_playlist_leave(self, data=None):
            data = data or dict()
            try:
                sid = flask.request.sid
                if not (request_id := data.get('request_id', None)):
                    self.response(
                        0,
                        self.CommonSocketIOPayload.PAYLOAD_REQUIRED_OMITTED | {'data': {'omitted': 'request_id'}})
                    return
                if not (sio_token_str := data.get('sio_token', None)):
                    self.response(
                        request_id,
                        self.CommonSocketIOPayload.PAYLOAD_REQUIRED_OMITTED | {'data': {'omitted': 'sio_token'}})
                    return
                if not (sio_csrf_token_str := data.get('sio_csrf_token', None)):
                    self.response(
                        request_id,
                        self.CommonSocketIOPayload.PAYLOAD_REQUIRED_OMITTED | {'data': {'omitted': 'sio_csrf_token'}})
                    return
                if not (pid := utils.safe_int(data.get('playlist_id', None))):
                    self.response(
                        request_id,
                        self.CommonSocketIOPayload.PAYLOAD_REQUIRED_OMITTED | {'data': {'omitted': 'playlist_id'}})
                    return

                if room_data := PlayCoWebsocket.redis_mgr.exit_room(pid, sid, sio_token_str, sio_csrf_token_str):
                    self.broadcast_on_room(
                        pid=pid, event=self.ResponseEventType.PLAYLIST_USER_EXITED.value,
                        data=self.CommonSocketIOPayload.USER_LEFT_SELF | {
                            'data': {'room': PlayCoWebsocket.redis_mgr.room_publicify(room_data), }
                        },
                        send_to_requester=True)
                    flask_socketio.leave_room(room=pid, sid=sid, namespace=PlayCoWebsocket.namespace)
                    self.response(request_id, self.CommonSocketIOPayload.USER_LEFT_SELF)
                else:
                    flask_socketio.close_room(room=pid, namespace=PlayCoWebsocket.namespace)
                    self.response(request_id, self.CommonSocketIOPayload.ROOM_CLOSED)

            except pyjwt_exc.ExpiredSignatureError:  # Token is too old!
                self.response(request_id, self.CommonSocketIOPayload.SIO_TOKEN_EXPIRED)
            except pyjwt_exc.PyJWTError:  # Token is invalid!
                self.response(request_id, self.CommonSocketIOPayload.SIO_TOKEN_INVALID)
            except KeyError as err:
                if str(err).startswith('Session'):  # Session not found. Disconnect the client!
                    self.response(request_id, self.CommonSocketIOPayload.SESSION_NOT_EXIST)
                    self.disconnect(sid)
                else:  # Playlist room not found.
                    self.response(request_id, self.CommonSocketIOPayload.ROOM_NOT_EXIST)
            except Exception as err:  # Unknown exception raised, like RedisCommitFailure.
                print(utils.get_traceback_msg(err), flush=True)
                self.response(request_id, self.CommonSocketIOPayload.SERVER_ERROR)

        # Event handler function
        def on_playlist_set_status(self, data=None):
            data = data or dict()
            try:
                sid = flask.request.sid
                if not (request_id := data.get('request_id', None)):
                    self.response(
                        0,
                        self.CommonSocketIOPayload.PAYLOAD_REQUIRED_OMITTED | {'data': {'omitted': 'request_id'}})
                    return
                if not (sio_token_str := data.get('sio_token', None)):
                    self.response(
                        request_id,
                        self.CommonSocketIOPayload.PAYLOAD_REQUIRED_OMITTED | {'data': {'omitted': 'sio_token'}})
                    return
                if not (sio_csrf_token_str := data.get('sio_csrf_token', None)):
                    self.response(
                        request_id,
                        self.CommonSocketIOPayload.PAYLOAD_REQUIRED_OMITTED | {'data': {'omitted': 'sio_csrf_token'}})
                    return
                if not (pid := utils.safe_int(data.get('playlist_id', None))):
                    self.response(
                        request_id,
                        self.CommonSocketIOPayload.PAYLOAD_REQUIRED_OMITTED | {'data': {'omitted': 'playlist_id'}})
                    return

                # utils.safe_int returns 0, and 0 is a valid index, but it's false.
                safe_int_none = utils.ignore_exception(Exception, None)(int)
                currently_playing: int | None = safe_int_none(data.get('currently_playing', None))
                if currently_playing is None:
                    self.response(
                        request_id,
                        self.CommonSocketIOPayload.PAYLOAD_REQUIRED_OMITTED | {
                            'data': {'omitted': 'currently_playing', }})
                    return

                if not (target_room := PlayCoWebsocket.redis_mgr.get_room(pid)):
                    self.response(request_id, self.CommonSocketIOPayload.ROOM_NOT_EXIST)
                    return
                if not (target_room_sid := target_room.get('sid', {}).get(sid)):
                    self.response(request_id, self.CommonSocketIOPayload.SESSION_NOT_EXIST)
                    return

                # Update session status
                session_status = target_room_sid['status']
                session_status['currently_playing'] = currently_playing

                # Commit to redis
                PlayCoWebsocket.redis_mgr.update_session_status_on_room(
                    pid, sid, sio_token_str, sio_csrf_token_str, session_status)
                self.broadcast_updated_status_on_room(pid)
                self.response(request_id, self.CommonSocketIOPayload.ROOM_MODIFIED)

            except pyjwt_exc.ExpiredSignatureError:  # Token is too old!
                self.response(request_id, self.CommonSocketIOPayload.SIO_TOKEN_EXPIRED)
            except pyjwt_exc.PyJWTError:  # Token is invalid!
                self.response(request_id, self.CommonSocketIOPayload.SIO_TOKEN_INVALID)
            except KeyError:  # Session does not exist!
                # But do not disconnect as we just checked if the session is in this room!
                self.response(request_id, self.CommonSocketIOPayload.SESSION_NOT_EXIST)
            except ValueError as err:  # Playlist does not exist or new_status is not valid.
                if str(err).startswith('Room'):
                    self.response(request_id, self.CommonSocketIOPayload.PLAYLIST_NOT_EXIST)
                # This is unexpected server error.
                print(utils.get_traceback_msg(err), flush=True)
                self.response(request_id, self.CommonSocketIOPayload.SERVER_ERROR)
            except Exception as err:  # Unknown exception raised, like RedisCommitFailure.
                print(utils.get_traceback_msg(err), flush=True)
                self.response(request_id, self.CommonSocketIOPayload.SERVER_ERROR)

        # Utility function
        def response(self, request_id: str, data: dict):
            return self.emit(
                event=self.ResponseEventType.REQUEST_RESPONSE.value + f'_{request_id}',
                data=data,
                room=flask.request.sid,  # Requester only
                namespace=PlayCoWebsocket.namespace,
                include_self=True)

        # Utility function
        def broadcast_on_room(self,
                              pid: int,
                              event: str,
                              data: dict,
                              send_to_requester: bool = False):
            return self.emit(
                event=event,
                data=data,
                room=pid,
                namespace=PlayCoWebsocket.namespace,
                include_self=send_to_requester)

        # Utility function
        @classmethod
        def broadcast_updated_status_on_room(cls, pid: int):
            room_data, is_room_data_modified = PlayCoWebsocket.redis_mgr.update_room_hash(pid)

            return PlayCoWebsocket.socketio_app.emit(
                event=cls.ResponseEventType.PLAYLIST_MODIFIED.value,
                data=cls.CommonSocketIOPayload.ROOM_MODIFIED | {
                    'data': {
                        'room': PlayCoWebsocket.redis_mgr.room_publicify(room_data) | {
                            'db_modified': is_room_data_modified,
                        },
                    }
                },
                to=pid,
                namespace=PlayCoWebsocket.namespace,
                include_self=True)

        # Utility function
        @classmethod
        def broadcast_official_announcement(cls, data):
            PlayCoWebsocket.socketio_app.emit(
                event=cls.ResponseEventType.OFFICIAL_ANNOUNCEMENT.value,
                args=data,
                namespace=PlayCoWebsocket.namespace,
                include_self=True)
