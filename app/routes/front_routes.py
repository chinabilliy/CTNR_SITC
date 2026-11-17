# -*- coding: utf-8 -*-
"""前台：提箱登记录入、Excel 导入、列表。"""
import os
from datetime import datetime
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, send_file)
from werkzeug.utils import secure_filename
from ..auth import require_role, current_user
from ..db import get_db, now, immediate, backup_db
from ..services import excel_io
from .. import config

bp = Blueprint("front", __name__)


@bp.route("/")
@require_role("front.pickups")
def index():
    return redirect(url_for("front.pickups"))


@bp.route("/pickups")
@require_role("front.pickups")
def pickups():
    db = get_db()
    rows = db.execute(
        "SELECT p.*, y.short_name AS yard_short, "
        "(SELECT COUNT(*) FROM eir_records e WHERE e.pickup_id=p.id) AS eir_count, "
        "(SELECT GROUP_CONCAT(DISTINCT e.lease_no_snapshot) FROM eir_records e "
        " WHERE e.pickup_id=p.id) AS allocated_lease_no "
        "FROM pickups p JOIN yards y ON y.id=p.yard_id ORDER BY p.id DESC"
    ).fetchall()
    yards = db.execute("SELECT * FROM yards ORDER BY short_name").fetchall()
    return render_template("front/pickups.html", rows=rows, yards=yards)


@bp.route("/pickups/add", methods=["GET", "POST"])
@require_role("front.pickups")
def pickup_add():
    db = get_db()
    if request.method == "POST":
        f = request.form
        try:
            qty = int(f.get("quantity", "0"))
            if qty <= 0:
                raise ValueError
        except ValueError:
            flash("数量必须是正整数", "err")
            return redirect(url_for("front.pickup_add"))
        ctype = f.get("container_type", "")
        if ctype not in config.CONTAINER_TYPES:
            flash("箱型非法", "err")
            return redirect(url_for("front.pickup_add"))
        db.execute(
            "INSERT INTO pickups(vessel,voyage,bl_no,container_type,quantity,yard_id,"
            "requested_lease_no,eir_print_count,status,created_by,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,0,'pending',?,?,?)",
            (f.get("vessel", "").strip(), f.get("voyage", "").strip(), f.get("bl_no", "").strip(),
             ctype, qty, int(f.get("yard_id", "0")), f.get("lease_no", "").strip() or None,
             current_user()["id"], now(), now()),
        )
        db.commit()
        flash("提箱登记已添加", "ok")
        return redirect(url_for("front.pickups"))
    yards = db.execute("SELECT * FROM yards ORDER BY short_name").fetchall()
    return render_template("front/pickup_add.html", yards=yards, types=config.CONTAINER_TYPES)


@bp.route("/pickups/<int:pid>/edit", methods=["GET", "POST"])
@require_role("front.pickups")
def pickup_edit(pid):
    db = get_db()
    p = db.execute("SELECT * FROM pickups WHERE id=?", (pid,)).fetchone()
    if not p:
        flash("记录不存在", "err")
        return redirect(url_for("front.pickups"))
    if p["status"] != "pending":
        flash("已放箱的记录不能修改", "err")
        return redirect(url_for("front.pickups"))
    if request.method == "POST":
        f = request.form
        try:
            qty = int(f.get("quantity", "0"))
            if qty <= 0:
                raise ValueError
        except ValueError:
            flash("数量必须是正整数", "err")
            return redirect(url_for("front.pickup_edit", pid=pid))
        db.execute(
            "UPDATE pickups SET vessel=?,voyage=?,bl_no=?,container_type=?,quantity=?,"
            "yard_id=?,requested_lease_no=?,updated_at=? WHERE id=?",
            (f.get("vessel", "").strip(), f.get("voyage", "").strip(), f.get("bl_no", "").strip(),
             f.get("container_type", ""), qty, int(f.get("yard_id", "0")),
             f.get("lease_no", "").strip() or None, now(), pid),
        )
        db.commit()
        flash("已保存", "ok")
        return redirect(url_for("front.pickups"))
    yards = db.execute("SELECT * FROM yards ORDER BY short_name").fetchall()
    return render_template("front/pickup_edit.html", p=p, yards=yards, types=config.CONTAINER_TYPES)


@bp.route("/pickups/<int:pid>/delete", methods=["POST"])
@require_role("front.pickups")
def pickup_delete(pid):
    db = get_db()
    p = db.execute("SELECT status FROM pickups WHERE id=?", (pid,)).fetchone()
    if not p:
        flash("记录不存在", "err")
    elif p["status"] != "pending":
        flash("已放箱的记录不能删除", "err")
    else:
        db.execute("DELETE FROM pickups WHERE id=?", (pid,))
        db.commit()
        flash("已删除", "ok")
    return redirect(url_for("front.pickups"))


@bp.route("/import", methods=["GET", "POST"])
@require_role("front.import_excel")
def import_excel():
    if request.method == "POST":
        file = request.files.get("file")
        if not file or not file.filename:
            flash("请选择文件", "err")
            return redirect(url_for("front.import_excel"))
        sheet = request.form.get("sheet", "pickups")
        tmp = os.path.join(config.BACKUP_DIR, "_import_tmp_" + secure_filename(file.filename))
        file.save(tmp)
        fn = {"yards": excel_io.import_yards,
              "batches": excel_io.import_batches,
              "pickups": excel_io.import_pickups}.get(sheet)
        if not fn:
            flash("未知导入类型", "err")
            return redirect(url_for("front.import_excel"))
        backup_db("before-import")
        res = fn(tmp, db=get_db(), commit=True, owner_id=current_user()["id"])
        os.remove(tmp)
        if not res.get("ok"):
            flash("导入失败：%s" % "; ".join("第%d行 %s" % (r, m) for r, m in res["errors"][:10]), "err")
        else:
            flash("导入成功：%s" % res, "ok")
        return redirect(url_for("front.import_excel"))
    return render_template("front/import.html")


@bp.route("/templates/<name>")
@require_role("front.import_excel")
def download_template(name):
    allowed = {"yards": "堆场信息_导入模板.xlsx",
               "batches": "起租号登记_导入模板.xlsx",
               "pickups": "提箱登记_导入模板.xlsx"}
    if name not in allowed:
        return "Not found", 404
    path = os.path.join(config.EXCEL_TEMPLATE_DIR, allowed[name])
    if not os.path.exists(path):
        excel_io.make_blank_import_templates()
    return send_file(path, as_attachment=True, download_name=allowed[name])
