import flask
import flask.views

import app.api.helper_class as api_class
import app.api.tool.network_packet_parser.packet_parser as packet_parser

from app.api.response_case import ResourceResponseCase


class NetworkPacketParserRoute(flask.views.MethodView, api_class.MethodViewMixin):
    def get(self):
        '''
        description: Responses html page
        responses:
            - resource_found
        '''
        return ResourceResponseCase.resource_found.create_response(
            content_type='text/html', template_path='network_packet_parser/index.html')

    @api_class.RequestBody(
        required_fields={'packet': {'type': 'string', }, },
        optional_fields={'include_data': {'type': 'boolean', }, }, )
    def post(self, req_body: dict):
        '''
        description: Parse and return a parsed result of network packet.
        responses:
            - resource_created
            - resource_prediction_failed
        '''
        try:
            return ResourceResponseCase.resource_created.create_response(
                data={
                    'packet_parser': packet_parser.frame_str(
                        packet_parser
                        .Ethernet(req_body.get('packet', ''))
                        .to_dict(include_frame_data=req_body.get('include_data', False))
                    ),
                },
            )
        except Exception as err:
            return ResourceResponseCase.resource_prediction_failed.create_response(
                data={'prediction_failed_reason': [str(err), ]})


network_packet_parser_resource_route = {
    '/tool/npp': NetworkPacketParserRoute,
}
