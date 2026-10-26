"""Route definitions: declare endpoints and delegate to the controllers."""
from flask import Blueprint
from flask_cors import cross_origin

from src.controllers import printer_controller

printer_bp = Blueprint('printer', __name__)


@printer_bp.route('/printers', methods=['GET'])
@cross_origin()
def list_printers():
    return printer_controller.list_printers_controller()


@printer_bp.route('/printers/selected', methods=['GET'])
@cross_origin()
def get_selected_printer():
    return printer_controller.get_selected_printer_controller()


@printer_bp.route('/printers/selected', methods=['POST'])
@cross_origin()
def set_selected_printer():
    return printer_controller.set_selected_printer_controller()


@printer_bp.route('/print', methods=['POST'])
@cross_origin()
def print_endpoint():
    return printer_controller.print_controller()


@printer_bp.route('/render', methods=['POST'])
@cross_origin()
def render_endpoint():
    return printer_controller.render_controller()


@printer_bp.route('/print/test', methods=['GET', 'POST'])
@cross_origin()
def print_test_endpoint():
    return printer_controller.print_test_controller()


@printer_bp.route('/print/test-label', methods=['GET', 'POST'])
@cross_origin()
def print_test_label_endpoint():
    return printer_controller.print_label_test_controller()


@printer_bp.route('/open-withdrawer', methods=['POST'])
@cross_origin()
def open_withdrawer_endpoint():
    return printer_controller.open_withdrawer_controller()
