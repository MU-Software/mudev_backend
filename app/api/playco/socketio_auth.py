import datetime
import flask
import flask.views
import secrets

import app.common.utils as utils
import app.api.helper_class as api_class
import app.database as db_module
import app.database.jwt as jwt_module
import app.plugin.playco.redis_db as playco_redis_module

from app.api.response_case import ResourceResponseCase

db = db_module.db


class PlayCoSocketIOAuthRoute(flask.views.MethodView, api_class.MethodViewMixin):
    @api_class.RequestHeader(auth={api_class.AuthType.Bearer: True, })
    @api_class.RequestBody(
        required_fields={
            'sid': {'type': 'string', },
            'sio_csrf_token': {'type': 'string', },
        }, )
    def post(self, req_header: dict, req_body: dict, access_token: jwt_module.AccessToken):
        '''
        description: Generate new token for the Socket.IO Connection.
        responses:
            - resource_created
        '''
        secret_key = flask.current_app.config.get('SECRET_KEY')
        sid = req_body['sid']
        sio_csrf_token = req_body['sio_csrf_token']

        sio_token = playco_redis_module.PlayCoToken()
        sio_token.exp = datetime.datetime.utcnow().replace(microsecond=0, tzinfo=utils.UTC)
        sio_token.exp += playco_redis_module.sio_token_valid_duration
        sio_token.user = access_token.user
        sio_token.jti = secrets.randbits(32)
        sio_token.sid = sid
        sio_token_jwt = sio_token.create_token(secret_key+sid+sio_csrf_token)

        return ResourceResponseCase.resource_created.create_response(
            data={'sio_token': {'exp': sio_token.exp, 'token': sio_token_jwt, }, }, )
