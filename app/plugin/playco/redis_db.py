import copy
import datetime
import flask
import json
import typing

import app.common.utils as utils
import app.database as db_module
import app.database.user as user_module
import app.database.jwt as jwt_module
import app.database.playco.playlist as playlist_module

MAX_CONNECTIONS_PER_USER = 5

db = db_module.db
redis_db = db_module.redis_db

# Socket.IO token will expire after 1 hour
sio_token_valid_duration: datetime.timedelta = datetime.timedelta(hours=1)


class PlayCoToken(jwt_module.TokenBase):
    ALLOWED_CLAIM = ['api_ver', 'iss', 'exp', 'user', 'sub', 'jti', 'sid']
    sub: str = 'Playco_SIO'  # Token name
    sid: str = ''  # Session ID (only used in PlayCoToken)


class PlayCoRedis:
    __root_key__: str = 'redis.playco'

    #: description:
    #:   user information storage
    #: structure:
    #:   user_id(uid):
    #:     type: ['string:object']
    #:     contains:
    #:       sid:
    #:         type: [null, 'string']
    #:       nickname:
    #:         type: ['string']
    User = typing.TypedDict('User', {
        'sid': list[tuple[str, int]],
        'nickname': str,
        'nickname_counter': int,
    })
    __redis_user_rec_key__ = __root_key__ + '.users.{}'

    #: description:
    #:   session storage
    #: structure:
    #:   session_id(sid):
    #:     type: ['string:object']
    #:     contains:
    #:       nickname:
    #:         type: ['string']
    #:       sio_token:
    #:         type: ['string']
    #:       entered_room:
    #:         type: ['list[string]', ]
    Session = typing.TypedDict('Session', {
        'user_id': int,
        'nickname': str,
        'entered_room': list[str]
    })
    __redis_session_key__ = __root_key__ + '.sessions.{}'

    #: description:
    #:   room information storage
    #: structure:
    #:   room_uuid(playlist_uuid):
    #:     type: ['string:object']
    #:     description:
    #:       I know playlist_uuid is int, but we need to set room id as string
    #:     contains:
    #:       sid:
    #:         type: ['string:object']
    #:         contains:
    #:           status:
    #:             type: ['object']
    #:             contains:
    #:               currently_playing:
    #:                 type: ['number']
    #:           data:
    #:             type: ['string:object']
    #:       current_play_target_sid:
    #:         type: ['string']
    #:       playlist_hash:
    #:         type: ['string']
    Status = typing.TypedDict('Status', {
        'currently_playing': int,
    })
    Participant = typing.TypedDict('Participant', {
        'status': Status,
        'nickname': str,
        'data': dict[str, typing.Any],
    })
    Room = typing.TypedDict('Room', {
        'playlist_id': int,
        'current_play_target_sid': str | None,
        'playlist_hash': str,
        'sid': dict[str, Participant]
    })
    __redis_room_key__ = __root_key__ + '.rooms.{}'

    def _add_sid_to_userrec(self, uid: int, sid: str) -> tuple[str, int]:
        target_redis_key = self.__redis_user_rec_key__.format(uid)

        if not (target_user_rec := json.loads(redis_db.get(target_redis_key) or '{}')):
            # This user doesn't have any previous session, Let's create one.
            if not (target_user := db.session.query(user_module.User).filter(user_module.User.uuid == uid).first()):
                raise KeyError('User not found')
            target_user_rec = self.User(sid=[], nickname=target_user.nickname, nickname_counter=0)
        target_user_rec = self.User(target_user_rec)  # This is for type-hint

        if len(target_user_rec['sid']) > MAX_CONNECTIONS_PER_USER:
            # User already has more than 5 connections on a playco service
            raise OverflowError('len(target_user_rec[\'sid\']) > MAX_CONNECTIONS_PER_USER')

        target_user_sid_collection = [sid for sid, snum in target_user_rec['sid']]
        if sid in target_user_sid_collection:
            # User is already on a session
            session_index = target_user_sid_collection.index(sid)
            return target_user_rec['sid'][session_index]

        target_user_rec['nickname_counter'] += 1
        target_user_rec['sid'].append((sid, target_user_rec['nickname_counter']))
        redis_db.set(target_redis_key, json.dumps(target_user_rec))
        return target_user_rec['nickname'], target_user_rec['nickname_counter']

    def _del_sid_from_userrec(self, uid: int, sid: str):
        target_redis_key = self.__redis_user_rec_key__.format(uid)

        if not (target_user_rec := json.loads(redis_db.get(target_redis_key) or '{}')):
            # Cannot found any session data of this user.
            return
        target_user_rec = self.User(target_user_rec)  # This is for type-hint

        target_user_sid_collection = [sid for sid, snum in target_user_rec['sid']]
        if sid in target_user_sid_collection:
            # User is on a session
            session_index = target_user_sid_collection.index(sid)
            del(target_user_rec['sid'][session_index])

        if not target_user_rec['sid']:
            # There's no session for this user, so destroy this.
            redis_db.delete(target_redis_key)
        else:
            redis_db.set(target_redis_key, json.dumps(target_user_rec))

    def create_session(self, sid: str, sio_token_str: str, sio_csrf_token_str: str):
        # We need to check SIO token, and it'll be automatically checked while we are parsing.
        # Actually, we don't need to check if the token is paired with SessionID
        # as SessionID is used as a key on encryption.
        sio_token = PlayCoToken.from_token(
            sio_token_str,
            flask.current_app.config.get('SECRET_KEY')+sid+sio_csrf_token_str)

        # Check if the session already exists
        if self.get_session(sid):
            raise KeyError('Session already exists')

        # Add session on user record.
        # Notes that more than {MAX_CONNECTIONS_PER_USER} sessions cannot be connected,
        # if this happens, then OverflowError will be raised!
        nickname, session_num = self._add_sid_to_userrec(sio_token.user, sid)

        # Add new session on Redis
        target_session = self.Session(
            user_id=sio_token.user,
            nickname=f'{nickname}#{session_num}',
            entered_room=[])

        try:
            if not self.set_session(sid, target_session):
                raise Exception
        except Exception:
            raise Exception('Redis commit failed while creating session! Call an ambulance!')

    def destroy_session(self, sid: str, need_room_cleanup: bool = False):
        # We cannot check SIO token here, as user cannot send token to us when they disconnect.

        # Check if the session exists
        if not (target_session := self.get_session(sid)):
            return

        # Delete sid from user record
        self._del_sid_from_userrec(target_session['user_id'], sid)

        if need_room_cleanup:
            # Exit room if session is entered, and remove target session
            for room_id in target_session['entered_room']:
                try:
                    self.exit_room(room_id, sid, '', '', True)
                except Exception as err:
                    # This can be happened when only user in playlist disconnects.
                    print(utils.get_traceback_msg(err), flush=True)

        try:
            if not redis_db.delete(self.__root_key__ + f'.sessions.{sid}'):
                raise Exception
        except Exception:
            raise Exception('Redis commit failed while deleting session! Call an ambulance!')

    def set_session(self, sid: str, value: Session):
        return redis_db.set(self.__root_key__ + f'.sessions.{sid}', json.dumps(value))

    def get_session(self, sid: str) -> Session | None:
        redis_result = redis_db.get(self.__root_key__ + f'.sessions.{sid}')
        return json.loads(redis_result) if redis_result else None

    def set_room(self, pid: int, value: Room):
        return redis_db.set(self.__redis_room_key__.format(pid), json.dumps(value))

    def get_room(self, pid: int) -> Room | None:
        redis_result = redis_db.get(self.__redis_room_key__.format(pid))
        print(redis_result, flush=True)
        return json.loads(redis_result) if redis_result else None

    def get_rooms(self, pid_list: list[int]) -> dict[int, Room] | None:
        redis_pid_keys = [self.__redis_room_key__.format(z) for z in pid_list]
        redis_query_result_raw = [utils.safe_json_loads(z) for z in redis_db.mget(redis_pid_keys)]
        redis_query_result = [self.Room(z) for z in redis_query_result_raw if z]
        redis_result = {z['playlist_id']: z for z in redis_query_result if z}
        return redis_result if redis_result else None

    def get_room_participant_number(self, pid) -> int | None:
        room_result = self.get_room(pid)
        return len(room_result['sid']) if room_result else None

    def get_room_participants_number(self, pid_list: list[int]) -> dict[int, int] | None:
        room_result = self.get_rooms(pid_list)
        return {pid: len(room['sid']) for pid, room in room_result.items()} if room_result else None

    def update_room_hash(self, pid: int) -> tuple[Room, bool]:
        # Returns (room_redis_data, is_room_data_modified)

        if not (room_redis_result := self.get_room(pid)):
            raise KeyError('Room does not exist')

        if not (room_db_result := db.session.query(playlist_module.Playlist)
                .filter(playlist_module.Playlist.uuid == pid).first()):
            raise KeyError('Playlist does not exist')

        if room_redis_result['playlist_hash'] == room_db_result.get_hash():
            return room_redis_result, False

        room_redis_result['playlist_hash'] = room_db_result.get_hash()
        self.set_room(pid, room_redis_result)
        return room_redis_result, True

    def enter_room(self, pid: int, sid: str, sio_token_str: str, sio_csrf_token_str: str) -> Room:
        # We need to check SIO token, and it'll be automatically checked while we are parsing.
        # Actually, we don't need to check if the token is paired with SessionID
        # as SessionID is used as a key on encryption.
        sio_token = PlayCoToken.from_token(  # noqa: F841
            sio_token_str,
            flask.current_app.config.get('SECRET_KEY')+sid+sio_csrf_token_str)

        # TODO: Need to check if session can enter this room(AUTHORIZATION)
        # TODO: Need to recalculate current_play_target_sid

        # Try to get user session data, and if it's not exist, then raise KeyError
        if not (target_session := self.get_session(sid)):
            raise KeyError('Session does not exist')

        # Try to get room, and if it's not exist, then try to create it.
        if not (target_room := self.get_room(pid)):
            # OK, room does not exist, Let's create the room.
            # Check if the playlist exists on DB
            if not (target_playlist_db := db.session.query(playlist_module.Playlist)
                    .filter(playlist_module.Playlist.uuid == pid).first()):
                raise ValueError(f'Playlist ID:{pid} does not exist')

            target_room = self.Room(
                playlist_id=pid,
                playlist_hash=target_playlist_db.get_hash(),
                sid=dict(), current_play_target_sid=None)

        # Let's add user to room and also add room to user session
        target_room['sid'][sid] = self.Participant(
            status=self.Status(currently_playing=0), data={}, nickname=target_session['nickname'])
        if pid not in target_session['entered_room']:
            target_session['entered_room'].append(pid)

        # Commit to redis
        try:
            if not all((self.set_room(pid, target_room), self.set_session(sid, target_session), )):
                raise Exception
        except Exception:
            raise Exception('Redis commit failed while entering the room! Call an ambulance!')

        return target_room

    def exit_room(self,
                  pid: int,
                  sid: str,
                  sio_token_str: str,
                  sio_csrf_token_str: str,
                  force: bool = False) -> Room | None:
        if not force:
            # We need to check SIO token, and it'll be automatically checked while we are parsing.
            # Actually, we don't need to check if the token is paired with SessionID
            # as SessionID is used as a key on encryption.
            sio_token = PlayCoToken.from_token(  # noqa: F841
                sio_token_str,
                flask.current_app.config.get('SECRET_KEY')+sid+sio_csrf_token_str)

        # Try to get user session data and room data.
        # If one of data does not exist, then raise KeyError
        target_session = self.get_session(sid)
        target_room = self.get_room(pid)
        if not all((target_session, target_room, )):
            raise KeyError(f'{"Session" if not target_session else "Room"} does not exist!')

        # TODO: Need to recalculate current_play_target_sid

        # Let's erase user from room and also erase room from user session
        target_room['sid'].pop(sid, {})
        if pid in target_session['entered_room']:
            target_session['entered_room'].remove(pid)

        # Commit session to redis first. Room needs more treatment.
        try:
            if not self.set_session(sid, target_session):
                raise Exception
        except Exception:
            raise Exception('Redis commit failed while saving session on exit! Call an ambulance!')

        # If there's no one in this room, then delete room.
        try:
            if not len(target_room['sid']):
                redis_db.delete(self.__redis_room_key__.format(pid))
                target_room = None
            else:
                if not self.set_room(pid, target_room):
                    raise Exception
        except Exception:
            raise Exception('Redis commit failed while saving room on exit! Call an ambulance!')

        return target_room

    def update_session_status_on_room(self,
                                      pid: int,
                                      sid: str,
                                      sio_token_str: str,
                                      sio_csrf_token_str: str,
                                      new_status: 'PlayCoRedis.Status') -> Room:
        # We need to check SIO token, and it'll be automatically checked while we are parsing.
        # Actually, we don't need to check if the token is paired with SessionID
        # as SessionID is used as a key on encryption.
        sio_token = PlayCoToken.from_token(  # noqa: F841
            sio_token_str,
            flask.current_app.config.get('SECRET_KEY')+sid+sio_csrf_token_str)

        # Try to get room data.
        if not (target_room := self.get_room(pid)):
            raise ValueError('Room does not exist!')

        # Check if the new data is valid.
        session_status_typehint = typing.get_type_hints(self.Status)
        # Is new data dictionary?
        if not isinstance(new_status, dict):
            raise ValueError('new_status is not a dict')
        # Does new data have all fields?
        if set(session_status_typehint.keys()) != set(new_status.keys()):
            raise ValueError('new_status fields are not matched with SessionStatus')
        # Does new data field value have proper types?
        for field_name, field_type in session_status_typehint.items():
            if not isinstance(new_status[field_name], field_type):
                err_str = f'new_status[\'{field_name}\'] type must be "{field_type}", '
                err_str += f'not {type(new_status[field_name])}'
                raise ValueError(err_str)

        # Check if session is in this room
        if sid not in target_room['sid']:
            raise KeyError('Session not in this room!')

        # Update session data on room.
        target_room['sid'][sid]['status'] = new_status

        # Commit room.
        try:
            if not self.set_room(pid, target_room):
                raise Exception
        except Exception:
            raise Exception('Redis commit failed while saving room on exit! Call an ambulance!')

        return target_room

    @staticmethod
    def room_publicify(data: 'PlayCoRedis.Room'):
        data = copy.deepcopy(data)
        sid_data = data.pop('sid', {})
        current_play_target_sid = data.pop('current_play_target_sid')

        # We need to change sid related keys in data to nickname
        data['participants'] = {v['nickname']: v for v in sid_data.values()}
        data['current_play_target'] = sid_data[current_play_target_sid]['nickname'] if current_play_target_sid else None

        return data
