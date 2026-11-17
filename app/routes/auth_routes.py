# -*- coding: utf-8 -*-
from flask import Blueprint, render_template, request, redirect, url_for, flash
from ..auth import try_login, logout, login_required, role_perms

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = try_login(request.form.get("username", ""), request.form.get("password", ""))
        if user:
            flash("欢迎，%s" % (user["display_name"] or user["username"]), "ok")
            nxt = request.args.get("next")
            if nxt:
                return redirect(nxt)
            # 按权限点决定落地页，兼容自定义角色（如合并角色）
            perms = role_perms(user["role"])
            if "front.pickups" in perms:
                return redirect(url_for("front.pickups"))
            if "print.print_list" in perms:
                return redirect(url_for("print.print_list"))
            if "admin.dashboard" in perms:
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("auth.login"))
        flash("账号或密码错误", "err")
    return render_template("login.html")


@bp.route("/logout")
@login_required
def logout_view():
    logout()
    flash("已退出", "ok")
    return redirect(url_for("auth.login"))
