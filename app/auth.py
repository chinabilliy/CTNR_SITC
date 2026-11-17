# -*- coding: utf-8 -*-
"""登录、会话与基于「角色 → 权限点」的访问控制。

权限点由 app/nav.py 的三级菜单派生（每个三级菜单项 = 一个权限点，key 为其
endpoint）。因此导航栏变更时，角色管理页的勾选项与鉴权白名单会自动同步。
"""
import json
from functools import wraps
from flask import session, redirect, url_for, abort, request
from werkzeug.security import generate_password_hash, check_password_hash
from .db import get_db, now

# 超级权限：拥有它即视为拥有全部权限点。内置管理员角色使用此标记，
# 这样以后在导航里新增菜单项，管理员无需重新授权即可访问。
SUPER_PERM = "admin"

ROLE_LABEL = {"printer": "打印员", "front": "前台录入", "admin": "管理员"}  # 角色表缺失时的兜底
# 角色表/权限点缺失时的兜底（与导航派生结果保持一致）
_FALLBACK_PERMS = {
    "admin": {SUPER_PERM},
    "front": {"front.pickups", "front.import_excel"},
    "printer": {"print.print_list"},
}


def all_permissions():
    """从导航菜单派生权限点清单 [(key, label), ...]。"""
    from .nav import collect_permissions
    return collect_permissions()


def all_perm_keys():
    return {k for k, _ in all_permissions()}


def role_info(key, conn=None):
    """返回角色的 label / perms / is_builtin；未知角色按无权限处理。"""
    row = (conn or get_db()).execute("SELECT * FROM roles WHERE key=?", (key,)).fetchone()
    if row:
        try:
            perms = set(json.loads(row["perms"] or "[]"))
        except (ValueError, TypeError):
            perms = set()
        return {"label": row["label"], "perms": perms, "is_builtin": bool(row["is_builtin"])}
    return {"label": ROLE_LABEL.get(key, key),
            "perms": set(_FALLBACK_PERMS.get(key, ())), "is_builtin": True}


def role_label(key):
    return role_info(key)["label"]


def role_perms(key):
    """角色实际拥有的权限点集合；含超级权限时展开为导航中的全部权限点。"""
    perms = role_info(key)["perms"]
    if SUPER_PERM in perms:
        return all_perm_keys()
    return perms


def is_admin(key):
    """是否为管理员角色（含超级权限标记）。"""
    return SUPER_PERM in role_info(key)["perms"]


def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    return get_db().execute("SELECT * FROM users WHERE id=? AND active=1", (uid,)).fetchone()


def try_login(username, password):
    row = get_db().execute("SELECT * FROM users WHERE username=? AND active=1", (username.strip(),)).fetchone()
    if not row or not check_password_hash(row["password_hash"], password or ""):
        return None
    get_db().execute("UPDATE users SET last_login_at=? WHERE id=?", (now(), row["id"]))
    get_db().commit()
    session["uid"] = row["id"]
    session["username"] = row["username"]
    session["role"] = row["role"]
    return row


def logout():
    session.clear()


def login_required(view):
    @wraps(view)
    def wrap(*a, **kw):
        if not current_user():
            return redirect(url_for("auth.login", next=request.path))
        return view(*a, **kw)
    return wrap


def require_role(perm):
    """鉴权：当前用户角色必须拥有指定权限点（通常为某个菜单 endpoint）。

    为兼容尚未改造的历史调用，perm 若仍传旧分组名，则映射到对应权限点判断。
    """
    def deco(view):
        @wraps(view)
        def wrap(*a, **kw):
            user = current_user()
            if not user:
                return redirect(url_for("auth.login", next=request.path))
            granted = role_perms(user["role"])
            need = perm
            if perm == SUPER_PERM:
                need = SUPER_PERM
            ok = (SUPER_PERM in granted) if need == SUPER_PERM else (need in granted)
            if not ok:
                abort(403)
            return view(*a, **kw)
        return wrap
    return deco


def hash_pwd(pwd):
    return generate_password_hash(pwd)
