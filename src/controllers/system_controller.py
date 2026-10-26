"""System controller: thin try/catch wrapper over the system service."""
from flask import jsonify, request

from src.services import system_service, version_service
from src.utils.response import error_response


def health_controller():
    try:
        result = system_service.get_health(request.headers.get(version_service.CLIENT_HEADER))
        code = 200 if result.get("status") == "success" else 400
        return jsonify(result), code
    except Exception as e:
        return jsonify(error_response(str(e))), 500
