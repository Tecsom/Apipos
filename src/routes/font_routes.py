"""Route definitions for the system font catalog: declare endpoints and delegate to the controllers."""
from flask import Blueprint
from flask_cors import cross_origin

from src.controllers import font_controller

font_bp = Blueprint('font', __name__)


@font_bp.route('/fonts', methods=['GET'])
@cross_origin()
def list_fonts():
    return font_controller.list_fonts_controller()
