# -*- coding: utf-8 -*-
"""后台：堆场/起租号 CRUD、放箱确认、图片上传、用户与设置。"""
import os
import re
import json
from datetime import datetime
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, send_file, abort, jsonify)
from werkzeug.utils import secure_filename
from ..auth import require_role, hash_pwd, current_user, all_permissions, role_info, SUPER_PERM
from ..db import get_db, now, immediate, backup_db, get_setting, set_setting
from ..services import allocation, eir_service, excel_io
from .. import config

bp = Blueprint("admin", __name__)


@bp.route("/admin")
@require_role("admin.dashboard")
def dashboard():
    db = get_db()
    def cnt(sql):
        return list(db.execute(sql).fetchone().values())[0]
    stats = {
        "yards": cnt("SELECT COUNT(*) AS n FROM yards"),
        "batches": cnt("SELECT COUNT(*) AS n FROM lease_batches"),
        "pending": cnt("SELECT COUNT(*) AS n FROM pickups WHERE status='pending'"),
        "released": cnt("SELECT COUNT(*) AS n FROM pickups WHERE status='released'"),
        "eirs": cnt("SELECT COUNT(*) AS n FROM eir_records"),
    }
    return render_template("admin/dashboard.html", stats=stats)


# ---------------- 堆场 ----------------
@bp.route("/admin/yards")
@require_role("admin.yards")
def yards():
    rows = get_db().execute("SELECT * FROM yards ORDER BY id").fetchall()
    return render_template("admin/yards.html", rows=rows)


@bp.route("/admin/yards/save", methods=["POST"])
@require_role("admin.yards")
def yard_save():
    db = get_db()
    f = request.form
    short = f.get("short_name", "").strip()
    full = f.get("full_name", "").strip()
    if not short or not full:
        flash("堆场全称和简称必填", "err")
        return redirect(url_for("admin.yards"))
    key = config.YARD_TEMPLATE_KEYS.get(short, "")
    if f.get("id"):
        db.execute(
            "UPDATE yards SET full_name=?,short_name=?,address=?,phone=?,work_hours=?,template_key=?,updated_at=? WHERE id=?",
            (full, short, f.get("address", "").strip(), f.get("phone", "").strip(),
             f.get("work_hours", "").strip(), key, now(), int(f["id"])),
        )
    else:
        db.execute(
            "INSERT INTO yards(full_name,short_name,address,phone,work_hours,template_key,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (full, short, f.get("address", "").strip(), f.get("phone", "").strip(),
             f.get("work_hours", "").strip(), key, now(), now()),
        )
    db.commit()
    flash("已保存", "ok")
    return redirect(url_for("admin.yards"))


@bp.route("/admin/yards/<int:yid>/delete", methods=["POST"])
@require_role("admin.yards")
def yard_delete(yid):
    db = get_db()
    try:
        db.execute("DELETE FROM yards WHERE id=?", (yid,))
        db.commit()
        flash("已删除", "ok")
    except Exception as e:
        db.rollback()
        flash("删除失败：该堆场已有关联数据", "err")
    return redirect(url_for("admin.yards"))


# ---------------- 起租号批次 ----------------
@bp.route("/admin/batches")
@require_role("admin.batches")
def batches():
    db = get_db()
    rows = db.execute(
        "SELECT b.*, y.short_name AS yard_short, "
        "(SELECT COUNT(*) FROM eir_records e WHERE e.batch_id=b.id) AS eir_count "
        "FROM lease_batches b "
        "JOIN yards y ON y.id=b.yard_id ORDER BY y.short_name, b.priority, b.id"
    ).fetchall()
    stock_map = {}
    for s in db.execute("SELECT batch_id,container_type,available FROM batch_stock"):
        stock_map.setdefault(s["batch_id"], {})[s["container_type"]] = s["available"]
    yards = db.execute("SELECT * FROM yards ORDER BY short_name").fetchall()
    return render_template("admin/batches.html", rows=rows, stock_map=stock_map, yards=yards, types=config.CONTAINER_TYPES)


@bp.route("/admin/batches/save", methods=["POST"])
@require_role("admin.batches")
def batch_save():
    db = get_db()
    f = request.form
    try:
        yard_id = int(f.get("yard_id", "0"))
        prio = int(f.get("priority", "99"))
    except ValueError:
        flash("参数错误", "err")
        return redirect(url_for("admin.batches"))
    lease = f.get("lease_no", "").strip()
    if not yard_id or not lease:
        flash("堆场和起租号必填", "err")
        return redirect(url_for("admin.batches"))
    bid = f.get("id")
    if bid:
        db.execute(
            "UPDATE lease_batches SET yard_id=?,lease_no=?,priority=?,remark=?,status=?,updated_at=? WHERE id=?",
            (yard_id, lease, prio, f.get("remark", "").strip(), f.get("status", "active"), now(), int(bid)),
        )
    else:
        cur = db.execute(
            "INSERT INTO lease_batches(yard_id,lease_no,priority,remark,status,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (yard_id, lease, prio, f.get("remark", "").strip(), f.get("status", "active"), now(), now()),
        )
        bid = cur.lastrowid
        for ct in config.CONTAINER_TYPES:
            raw = f.get("stock_" + ct, "").strip()
            if raw != "":
                db.execute(
                    "INSERT OR REPLACE INTO batch_stock(batch_id,container_type,available,updated_at) VALUES(?,?,?,?)",
                    (bid, ct, max(0, int(float(raw))), now()),
                )
    db.commit()
    flash("已保存", "ok")
    return redirect(url_for("admin.batches"))


@bp.route("/admin/batches/<int:bid>/stock", methods=["POST"])
@require_role("admin.batches")
def batch_stock_update(bid):
    db = get_db()
    for ct in config.CONTAINER_TYPES:
        key = "stock_" + ct
        if key not in request.form:
            continue
        raw = request.form[key].strip()
        if raw == "":
            db.execute("DELETE FROM batch_stock WHERE batch_id=? AND container_type=?", (bid, ct))
            continue
        val = max(0, int(float(raw)))
        db.execute(
            "INSERT INTO batch_stock(batch_id,container_type,available,updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(batch_id,container_type) DO UPDATE SET available=excluded.available,updated_at=excluded.updated_at",
            (bid, ct, val, now()),
        )
    db.commit()
    flash("库存已更新", "ok")
    return redirect(url_for("admin.batches"))


@bp.route("/admin/batches/<int:bid>/image", methods=["POST"])
@require_role("admin.batches")
def batch_image(bid):
    db = get_db()
    b = db.execute("SELECT * FROM lease_batches WHERE id=?", (bid,)).fetchone()
    if not b:
        abort(404)
    file = request.files.get("image")
    if not file or not file.filename:
        flash("请选择图片", "err")
        return redirect(url_for("admin.batches"))
    # 从原始文件名取扩展名：secure_filename 会剥掉中文（如"放箱通知单.png"→"png"），
    # 用它判断类型会把纯中文文件名的图片误判为无扩展名。保存名由系统生成，无路径风险。
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        flash("仅支持 png/jpg/jpeg/gif/webp", "err")
        return redirect(url_for("admin.batches"))
    lease_dir = os.path.join(config.UPLOAD_DIR, b["lease_no"])
    os.makedirs(lease_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    fname = "v%s%s" % (stamp, ext)
    path = os.path.join(lease_dir, fname)
    file.save(path)
    rel = "/uploads/release_notes/%s/%s" % (b["lease_no"], fname)
    db.execute("UPDATE lease_batches SET release_image_path=?,updated_at=? WHERE id=?", (rel, now(), bid))
    # 回写该批次已生成 EIR 的图片快照：支持「先放箱、后上传图片」，上传后打印立即显示新图。
    db.execute("UPDATE eir_records SET image_path_snapshot=? WHERE batch_id=?", (rel, bid))
    db.commit()
    flash("放箱图片已上传，已同步更新该批次 EIR", "ok")
    return redirect(url_for("admin.batches"))


@bp.route("/admin/batches/<int:bid>/delete", methods=["POST"])
@require_role("admin.batches")
def batch_delete(bid):
    """删除未放箱的起租号批次（已生成 EIR 的不允许删除）。"""
    db = get_db()
    b = db.execute("SELECT * FROM lease_batches WHERE id=?", (bid,)).fetchone()
    if not b:
        flash("批次不存在", "err")
        return redirect(url_for("admin.batches"))
    eir_count = db.execute(
        "SELECT COUNT(*) AS n FROM eir_records WHERE batch_id=?", (bid,)
    ).fetchone()["n"]
    if eir_count:
        flash("起租号 %s 已放箱（关联 %d 条 EIR），不能删除" % (b["lease_no"], eir_count), "err")
        return redirect(url_for("admin.batches"))
    backup_db("before-batch-delete")
    with immediate(db) as conn:
        conn.execute("DELETE FROM batch_stock WHERE batch_id=?", (bid,))
        conn.execute("DELETE FROM lease_batches WHERE id=?", (bid,))
    # 上传的放箱图片文件保留在磁盘，避免误删历史资料；仅移除数据库记录。
    flash("起租号 %s 已删除（库存记录一并清除）" % b["lease_no"], "ok")
    return redirect(url_for("admin.batches"))


# ---------------- 放箱确认 ----------------
@bp.route("/admin/release")
@require_role("admin.release_list")
def release_list():
    db = get_db()
    rows = db.execute(
        "SELECT p.*, y.short_name AS yard_short, "
        "(SELECT GROUP_CONCAT(DISTINCT e.lease_no_snapshot) FROM eir_records e "
        " WHERE e.pickup_id=p.id) AS allocated_lease_no "
        "FROM pickups p "
        "JOIN yards y ON y.id=p.yard_id ORDER BY p.status, p.id DESC"
    ).fetchall()
    batches = db.execute(
        "SELECT b.id,b.lease_no,b.priority,b.yard_id,y.short_name AS yard_short,"
        "s.container_type,s.available FROM lease_batches b "
        "JOIN yards y ON y.id=b.yard_id LEFT JOIN batch_stock s ON s.batch_id=b.id "
        "WHERE b.status='active' ORDER BY y.short_name,b.priority"
    ).fetchall()
    yards = db.execute("SELECT id,short_name FROM yards ORDER BY short_name").fetchall()
    return render_template("admin/release.html", rows=rows, batches=batches, yards=yards)


@bp.route("/admin/release/confirm", methods=["POST"])
@require_role("admin.release_list")
def release_confirm():
    ids = request.form.getlist("ids")
    if not ids:
        flash("请勾选要放箱的记录", "err")
        return redirect(url_for("admin.release_list"))
    manual = request.form.get("manual_batch", "").strip()
    manual_batch_id = int(manual) if manual else None
    ok, fail, changed = 0, [], 0
    backup_db("before-release")
    with immediate() as conn:
        for sid in ids:
            pid = int(sid)
            p = conn.execute("SELECT * FROM pickups WHERE id=?", (pid,)).fetchone()
            if not p:
                fail.append((pid, "记录不存在"))
                continue
            try:
                # 前台登记的堆场仅作参考：后台可逐票改堆场后再放箱。
                raw_yard = request.form.get("yard_%d" % pid, "").strip()
                target_yard = int(raw_yard) if raw_yard.isdigit() else p["yard_id"]
                if not conn.execute("SELECT 1 FROM yards WHERE id=?", (target_yard,)).fetchone():
                    raise allocation.AllocError("所选堆场不存在")
                yard_changed = target_yard != p["yard_id"]
                # 用副本参与分配与 EIR 生成，保证库存扣减、EIR 堆场快照都用新堆场。
                eff = dict(p)
                eff["yard_id"] = target_yard
                plan = allocation.allocate_one(
                    eff, conn, current_user()["id"], manual_batch_id,
                    respect_requested=not yard_changed,
                )
                eir_service.generate_for_plan(conn, eff, plan)
                if yard_changed:
                    conn.execute("UPDATE pickups SET yard_id=?,updated_at=? WHERE id=?",
                                 (target_yard, now(), pid))
                    changed += 1
                ok += 1
            except (allocation.AllocError, allocation.AlreadyReleased, ValueError) as e:
                fail.append((pid, str(e)))
                # 单条失败不回滚其它记录：只跳过该条
                continue
    suffix = "（其中 %d 条已改堆场）" % changed if changed else ""
    if fail:
        flash("放箱完成 %d 条%s；失败：%s" % (
            ok, suffix, "; ".join("ID%s %s" % x for x in fail[:5])), "err")
    else:
        flash("成功放箱 %d 条%s，EIR 已生成" % (ok, suffix), "ok")
    return redirect(url_for("admin.release_list"))


@bp.route("/admin/release/reset/<int:pid>", methods=["POST"])
@require_role("admin.release_list")
def release_reset(pid):
    """撤销放箱（仅当 EIR 未打印），库存回补。"""
    db = get_db()
    p = db.execute("SELECT * FROM pickups WHERE id=?", (pid,)).fetchone()
    if not p or p["status"] != "released":
        flash("记录状态不允许撤销", "err")
        return redirect(url_for("admin.release_list"))
    eirs = db.execute("SELECT * FROM eir_records WHERE pickup_id=?", (pid,)).fetchall()
    if any(e["print_count"] > 0 for e in eirs):
        flash("已有 EIR 打印过，不能撤销", "err")
        return redirect(url_for("admin.release_list"))
    with immediate(db) as conn:
        for e in eirs:
            conn.execute(
                "UPDATE batch_stock SET available=available+1 WHERE batch_id=? AND container_type=?",
                (e["batch_id"], p["container_type"]),
            )
        conn.execute("DELETE FROM eir_records WHERE pickup_id=?", (pid,))
        conn.execute(
            "UPDATE pickups SET status='pending',confirmed_by=NULL,confirmed_at=NULL,eir_print_count=0,updated_at=? WHERE id=?",
            (now(), pid),
        )
    flash("已撤销放箱，库存已回补", "ok")
    return redirect(url_for("admin.release_list"))


@bp.route("/admin/release/reset-print/<int:pid>", methods=["POST"])
@require_role("admin.release_list")
def release_reset_print(pid):
    """管理员重置该提单下所有 EIR 的打印次数为 0（前端已二次确认）。"""
    db = get_db()
    p = db.execute("SELECT id,bl_no,status FROM pickups WHERE id=?", (pid,)).fetchone()
    if not p or p["status"] != "released":
        flash("记录状态不允许重置打印次数", "err")
        return redirect(url_for("admin.release_list"))
    backup_db("before-reset-print")
    with immediate(db) as conn:
        conn.execute(
            "UPDATE eir_records SET print_count=0, printed_at=NULL WHERE pickup_id=?", (pid,)
        )
        conn.execute(
            "UPDATE pickups SET eir_print_count=0, updated_at=? WHERE id=?", (now(), pid)
        )
    flash("提单 %s 的 EIR 打印次数已重置为 0" % p["bl_no"], "ok")
    return redirect(url_for("admin.release_list"))


# ---------------- 角色管理 ----------------
@bp.route("/admin/roles")
@require_role("admin.roles")
def roles():
    db = get_db()
    rows = db.execute("SELECT * FROM roles ORDER BY is_builtin DESC, key").fetchall()
    for r in rows:
        try:
            r["perms_list"] = json.loads(r["perms"] or "[]")
        except (ValueError, TypeError):
            r["perms_list"] = []
    user_counts = {x["role"]: x["n"] for x in db.execute(
        "SELECT role, COUNT(*) AS n FROM users GROUP BY role")}
    from ..nav import permission_groups
    return render_template("admin/roles.html", rows=rows, all_perms=all_permissions(),
                           perm_groups=permission_groups(), user_counts=user_counts)


@bp.route("/admin/roles/save", methods=["POST"])
@require_role("admin.roles")
def role_save():
    db = get_db()
    f = request.form
    label = f.get("label", "").strip()
    perms = [p for p in f.getlist("perms") if p in dict(all_permissions())]
    perm_json = json.dumps(perms, ensure_ascii=False)
    old_key = f.get("id", "").strip()
    if old_key:
        old = db.execute("SELECT * FROM roles WHERE key=?", (old_key,)).fetchone()
        if not old:
            flash("角色不存在", "err")
        elif old["is_builtin"]:
            flash("内置角色不允许修改", "err")
        elif not label:
            flash("角色名称必填", "err")
        else:
            db.execute("UPDATE roles SET label=?,perms=?,updated_at=? WHERE key=?",
                       (label, perm_json, now(), old_key))
            db.commit()
            flash("角色已保存", "ok")
        return redirect(url_for("admin.roles"))
    key = f.get("key", "").strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,29}", key):
        flash("角色标识需为 2-30 位小写字母、数字或下划线，且以字母开头", "err")
    elif not label:
        flash("角色名称必填", "err")
    elif db.execute("SELECT 1 FROM roles WHERE key=?", (key,)).fetchone():
        flash("角色标识已存在", "err")
    else:
        db.execute(
            "INSERT INTO roles(key,label,perms,is_builtin,created_at,updated_at) "
            "VALUES(?,?,?,0,?,?)", (key, label, perm_json, now(), now()))
        db.commit()
        flash("角色已创建", "ok")
    return redirect(url_for("admin.roles"))


@bp.route("/admin/roles/<key>/delete", methods=["POST"])
@require_role("admin.roles")
def role_delete(key):
    db = get_db()
    r = db.execute("SELECT * FROM roles WHERE key=?", (key,)).fetchone()
    if not r:
        flash("角色不存在", "err")
    elif r["is_builtin"]:
        flash("内置角色不允许删除", "err")
    else:
        n = db.execute("SELECT COUNT(*) AS n FROM users WHERE role=?", (key,)).fetchone()["n"]
        if n:
            flash("还有 %d 个用户使用该角色，请先改派后再删除" % n, "err")
        else:
            backup_db("before-role-delete")
            db.execute("DELETE FROM roles WHERE key=?", (key,))
            db.commit()
            flash("角色已删除", "ok")
    return redirect(url_for("admin.roles"))


# ---------------- 导出 / 设置 / 用户 ----------------
@bp.route("/admin/export")
@require_role("admin.export_excel")
def export_excel():
    path = excel_io.export_workbook()
    return send_file(path, as_attachment=True, download_name=os.path.basename(path))


@bp.route("/admin/settings", methods=["GET", "POST"])
@require_role("admin.settings")
def settings():
    db = get_db()
    if request.method == "POST":
        for key in ("allow_split", "eir_no_prefix", "allow_reprint"):
            if key in request.form:
                set_setting(key, request.form[key].strip(), db)
        db.commit()
        flash("设置已保存", "ok")
    vals = {k: get_setting(k, db, "") for k in
            ("allow_split", "eir_no_prefix", "eir_seq", "eir_seq_date", "allow_reprint")}
    return render_template("admin/settings.html", vals=vals)


@bp.route("/admin/users")
@require_role("admin.users")
def users():
    db = get_db()
    rows = db.execute("SELECT id,username,role,display_name,active,last_login_at FROM users ORDER BY id").fetchall()
    roles = db.execute("SELECT key,label FROM roles ORDER BY is_builtin DESC, key").fetchall()
    return render_template("admin/users.html", rows=rows, roles=roles)


@bp.route("/admin/users/save", methods=["POST"])
@require_role("admin.users")
def user_save():
    db = get_db()
    f = request.form
    uid, username, pwd, role = f.get("id"), f.get("username", "").strip(), f.get("password", ""), f.get("role", "")
    if not username or not get_db().execute("SELECT 1 FROM roles WHERE key=?", (role,)).fetchone():
        flash("参数错误或角色不存在", "err")
        return redirect(url_for("admin.users"))
    if uid:
        if pwd:
            db.execute("UPDATE users SET username=?,password_hash=?,role=?,display_name=?,active=? WHERE id=?",
                       (username, hash_pwd(pwd), role, f.get("display_name", ""), int(bool(f.get("active"))), int(uid)))
        else:
            db.execute("UPDATE users SET username=?,role=?,display_name=?,active=? WHERE id=?",
                       (username, role, f.get("display_name", ""), int(bool(f.get("active"))), int(uid)))
    else:
        if not pwd:
            flash("新用户必须设置密码", "err")
            return redirect(url_for("admin.users"))
        db.execute(
            "INSERT INTO users(username,password_hash,role,display_name,active,created_at) VALUES(?,?,?,?,1,?)",
            (username, hash_pwd(pwd), role, f.get("display_name", ""), now()),
        )
    db.commit()
    flash("已保存", "ok")
    return redirect(url_for("admin.users"))


@bp.route("/admin/users/<int:uid>/delete", methods=["POST"])
@require_role("admin.users")
def user_delete(uid):
    db = get_db()
    target = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    me = current_user()
    if not target:
        flash("用户不存在", "err")
        return redirect(url_for("admin.users"))
    if me and me["id"] == uid:
        flash("不能删除当前登录的账号", "err")
        return redirect(url_for("admin.users"))
    # 防自锁：不能删除最后一个仍在启用的超级管理员
    if SUPER_PERM in role_info(target["role"], db)["perms"] and target["active"]:
        super_active = 0
        for u in db.execute("SELECT role, active FROM users WHERE active=1"):
            if SUPER_PERM in role_info(u["role"], db)["perms"]:
                super_active += 1
        if super_active <= 1:
            flash("不能删除最后一个启用的管理员", "err")
            return redirect(url_for("admin.users"))
    backup_db("before-user-delete")
    db.execute("DELETE FROM users WHERE id=?", (uid,))
    db.commit()
    flash("用户「%s」已删除，其关联记录的创建人/确认人已清空" % target["username"], "ok")
    return redirect(url_for("admin.users"))
