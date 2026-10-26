"""Flask application factory."""
from flask import Flask, request
from flask_cors import CORS

from src.config import APP_VERSION
from src.routes.font_routes import font_bp
from src.routes.printer_routes import printer_bp
from src.routes.system_routes import system_bp
from src.services import version_service


def create_app():
    app = Flask(__name__)
    app.config['CORS_HEADERS'] = ['Content-Type', version_service.CLIENT_HEADER]
    app.config['CORS_EXPOSE_HEADERS'] = [version_service.VERSION_HEADER]
    CORS(app, allow_headers=app.config['CORS_HEADERS'],
         expose_headers=app.config['CORS_EXPOSE_HEADERS'])
    app.register_blueprint(printer_bp)
    app.register_blueprint(system_bp)
    app.register_blueprint(font_bp)

    @app.before_request
    def _track_client_version():
        info = version_service.describe_client(request.headers.get(version_service.CLIENT_HEADER))
        if info:
            version_service.log_client_once(info)

    @app.after_request
    def _add_version_header(response):
        response.headers[version_service.VERSION_HEADER] = APP_VERSION
        return response

    return app
