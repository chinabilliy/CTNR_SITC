# -*- coding: utf-8 -*-
from flask import Flask
from . import config
from .db import close_db, init_db


def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["SESSION_COOKIE_HTTPONLY"] = config.SESSION_COOKIE_HTTPONLY
    app.config["SESSION_COOKIE_SAMESITE"] = config.SESSION_COOKIE_SAMESITE
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH

    init_db()
    app.teardown_appcontext(close_db)

    from .routes.auth_routes import bp as auth_bp
    from .routes.front_routes import bp as front_bp
    from .routes.admin_routes import bp as admin_bp
    from .routes.print_routes import bp as print_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(front_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(print_bp)

    @app.context_processor
    def inject_globals():
        from flask import request
        from .auth import current_user, role_label, role_perms
        from .nav import build_menu
        me = current_user()
        perms = role_perms(me["role"]) if me else set()
        return {
            "me": me,
            "role_label": role_label,
            "nav_menu": build_menu(perms, request.endpoint),
        }

    @app.errorhandler(403)
    def forbidden(_e):
        from flask import render_template
        return render_template("error.html", code=403, msg="没有权限执行此操作"), 403

    return app
