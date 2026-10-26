"""Controllers for the font catalog: a single try/catch per action, call the
service, send the response. No business logic lives here."""
from flask import jsonify, request

from src.services import font_service
from src.utils.coerce import truthy
from src.utils.response import error_response


def _respond(result):
    """Serialize a service result, deriving the HTTP status from its 'status' field."""
    code = 200 if result.get("status") == "success" else 400
    return jsonify(result), code


def list_fonts_controller():
    try:
        result = font_service.get_font_catalog(refresh=truthy(request.args.get('refresh')))
        return _respond(result)
    except Exception as e:
        return jsonify(error_response(str(e))), 500
