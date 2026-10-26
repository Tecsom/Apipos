"""Controllers: a single try/catch per action, call the service, send the response.

No business logic lives here. Services return the standardized response shape;
controllers only map it to an HTTP status code and serialize it.
"""
from flask import jsonify, request

from src.services import printer_service
from src.utils.response import error_response


def _respond(result):
    """Serialize a service result, deriving the HTTP status from its 'status' field."""
    code = 200 if result.get("status") == "success" else 400
    return jsonify(result), code


def list_printers_controller():
    try:
        result = printer_service.get_printers()
        return _respond(result)
    except Exception as e:
        return jsonify(error_response(str(e))), 500


def get_selected_printer_controller():
    try:
        result = printer_service.get_selected_printer()
        return _respond(result)
    except Exception as e:
        return jsonify(error_response(str(e))), 500


def set_selected_printer_controller():
    try:
        result = printer_service.set_selected_printer(request.get_json(silent=True))
        return _respond(result)
    except Exception as e:
        return jsonify(error_response(str(e))), 500


def print_controller():
    try:
        result = printer_service.print_job(request.get_json(silent=True))
        return _respond(result)
    except Exception as e:
        return jsonify(error_response(str(e))), 500


def render_controller():
    try:
        result = printer_service.render_job(request.get_json(silent=True))
        return _respond(result)
    except Exception as e:
        return jsonify(error_response(str(e))), 500


def open_withdrawer_controller():
    try:
        result = printer_service.open_drawer(request.get_json(silent=True))
        return _respond(result)
    except Exception as e:
        return jsonify(error_response(str(e))), 500


def print_test_controller():
    try:
        printer = request.args.get('printer')
        result = printer_service.print_test(printer)
        return _respond(result)
    except Exception as e:
        return jsonify(error_response(str(e))), 500


def print_label_test_controller():
    try:
        body = request.get_json(silent=True) or {}
        # Query params override the JSON body's label_settings.
        label_settings = dict(body.get('label_settings') or {})
        for key in ('width', 'height', 'unit'):
            if request.args.get(key):
                label_settings[key] = request.args.get(key)
        mode = request.args.get('mode') or body.get('mode') or body.get('pdf_mode')
        printer = request.args.get('printer') or body.get('printer')
        result = printer_service.print_label_test(printer, mode, label_settings or None)
        return _respond(result)
    except Exception as e:
        return jsonify(error_response(str(e))), 500
