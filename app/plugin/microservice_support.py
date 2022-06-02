import flask
import flask_socketio

import app.plugin.playco.websocket as playco_ws

socketio: flask_socketio.SocketIO = None
socketio_namespaces = [
    playco_ws.PlayCoWebsocket(),
]


def init_app(app: flask.Flask):
    restapi_version = app.config.get('RESTAPI_VERSION')

    allowed_origins: list = [f'https://{app.config.get("SERVER_NAME")}']
    local_client_port = app.config.get('LOCAL_DEV_CLIENT_PORT')
    if restapi_version == 'dev' and local_client_port:
        allowed_origins.append(f'http://localhost:{local_client_port}')
        allowed_origins.append(f'http://127.0.0.1:{local_client_port}')

    global socketio
    socketio = flask_socketio.SocketIO(
        app,
        path=f'/api/{restapi_version}/ws',
        cors_allowed_origins=allowed_origins,
        logger=True,
        engineio_logger=True)

    for namespace_def in socketio_namespaces:
        namespace_def.register_on_app(socketio)

    return socketio
