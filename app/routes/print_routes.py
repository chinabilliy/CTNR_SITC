# -*- coding: utf-8 -*-
"""打印：按提单号列出待打 EIR、打印页、点打印即累加次数。"""
import os
from flask import Blueprint, render_template, request, abort, send_from_directory, redirect, url_for, flash
from ..auth import require_role
from ..db import get_db, get_setting, immediate
from ..services import print_service
from .. import config

bp = Blueprint("print", __name__)


@bp.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(os.path.join(config.BASE_DIR, "uploads"), filename)


@bp.route("/print")
@require_role("print.print_list")
def print_list():
    db = get_db()
    reprint_on = get_setting("allow_reprint", db, "0") == "1"
    # 开关打开：可印张数=全部已放箱 EIR；关闭：仅未打印的
    pending_expr = "COUNT(e.id)" if reprint_on else \
                   "SUM(CASE WHEN e.print_count=0 THEN 1 ELSE 0 END)"
    rows = db.execute(
        "SELECT p.bl_no, p.vessel, p.voyage, p.status, p.eir_print_count, "
        "COUNT(e.id) AS total, "
        "SUM(CASE WHEN e.print_count>0 THEN 1 ELSE 0 END) AS printed_cnt, "
        + pending_expr + " AS pending "
        "FROM pickups p LEFT JOIN eir_records e ON e.pickup_id=p.id "
        "WHERE p.status='released' "
        "GROUP BY p.id ORDER BY p.id DESC"
    ).fetchall()
    return render_template("print/list.html", rows=rows, reprint_on=reprint_on)


@bp.route("/print/sheet")
@require_role("print.print_list")
def print_sheet():
    bl = request.args.get("bl", "").strip()
    bls_raw = request.args.get("bls", "").strip()
    ids_raw = request.args.get("ids", "")
    db = get_db()
    reprint_on = get_setting("allow_reprint", db, "0") == "1"
    if bls_raw:
        eirs = print_service.printable_by_bls(
            [x.strip() for x in bls_raw.split(",") if x.strip()], db,
            include_printed=reprint_on)
    elif bl:
        eirs = print_service.printable_by_bl(bl, db, include_printed=reprint_on)
    elif ids_raw:
        try:
            ids = [int(x) for x in ids_raw.split(",") if x.strip()]
        except ValueError:
            abort(400)
        # 开关关闭时 ids 路径只放行未打印 EIR，防构造 URL 绕过
        eirs = print_service.eirs_by_ids(ids, db, only_unprinted=not reprint_on)
    else:
        abort(400)
    if not eirs:
        flash("没有待打印的 EIR", "err")
        return redirect(url_for("print.print_list"))

    # 仅「开关打开 且 本批含已打印 EIR」时生成确认信息
    printed_counts = [e["print_count"] for e in eirs if e["print_count"] > 0]
    confirm_info = None
    if reprint_on and printed_counts:
        confirm_info = {
            "total": len(eirs),
            "reprint_count": len(printed_counts),
            "max_printed": max(printed_counts),
            "next_max": max(printed_counts) + 1,
        }
    return render_template("print/print_sheet.html", eirs=eirs, bl=bl,
                           stamp=request.args.get("stamp", ""),
                           confirm_info=confirm_info, reprint_on=reprint_on)


@bp.route("/print/mark", methods=["POST"])
@require_role("print.print_list")
def print_mark():
    # 兼容 ids=1,2,3 与 ids=1&ids=2&ids=3 两种传参
    parts = []
    for raw in request.form.getlist("ids"):
        parts.extend(x for x in raw.split(",") if x.strip())
    try:
        ids = [int(x) for x in parts]
    except ValueError:
        abort(400)
    with immediate() as conn:
        # 写事务内读开关，与管理员切换串行化
        reprint_on = get_setting("allow_reprint", conn, "0") == "1"
        if not reprint_on and ids:
            ph = ",".join("?" for _ in ids)
            already = conn.execute(
                "SELECT COUNT(*) AS c FROM eir_records "
                "WHERE id IN (%s) AND print_count>0" % ph,
                tuple(ids),
            ).fetchone()["c"]
            if already:
                return {"ok": False,
                        "msg": "系统未允许重印已打印的 EIR，请让管理员开启开关"}, 403
        affected = print_service.mark_printed(ids, conn, allow_reprint=reprint_on)
    return {"ok": True, "marked": affected}


@bp.route("/print/help")
@require_role("print.print_list")
def print_help():
    return render_template("print/help.html")
