# -*- coding: utf-8 -*-
"""SQLite 连接工厂、schema 初始化、事务上下文与备份。"""
import os
import json
import sqlite3
import shutil
from contextlib import contextmanager
from datetime import datetime
from flask import g
from . import config

DEFAULT_SETTINGS = {
    "eir_seq_date": "",
    "eir_seq": "0",
    "eir_no_prefix": "EIR",
    "allow_split": "1",
    "mark_print_after_confirm": "0",
    "allow_reprint": "0",
    "ui_theme": "default",
}

# 内置角色的权限点 = 导航菜单 endpoint（与 app/nav.py 保持一致）。
# 管理员用超级权限标记 SUPER_PERM，新增菜单后自动拥有。
BUILTIN_ROLES = {
    "admin": ("管理员", ["admin"]),
    "front": ("前台录入", ["front.pickups", "front.import_excel"]),
    "printer": ("打印员", ["print.print_list"]),
}


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _dict_factory(cursor, row):
    # dict 可直接被 json/tojson 序列化；Jinja 中 r.id 会自动回退到 r['id']
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


def connect():
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = _dict_factory
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _migrate_users_role(conn):
    """旧库 users.role 带 CHECK 约束，需重建表才能使用自定义角色。"""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    if not row or "CHECK(role IN" not in row["sql"]:
        return False
    conn.execute("PRAGMA foreign_keys=OFF")
    # 关键：新版 SQLite 的 RENAME 会把其它表的外键引用一并改写成 users_legacy，
    # 导致之后删除旧表后 pickups.confirmed_by 等外键悬空。开启兼容模式可避免。
    conn.execute("PRAGMA legacy_alter_table=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("ALTER TABLE users RENAME TO users_legacy")
        conn.execute(
            "CREATE TABLE users ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "username TEXT NOT NULL UNIQUE, "
            "password_hash TEXT NOT NULL, "
            "role TEXT NOT NULL, "
            "display_name TEXT, "
            "active INTEGER NOT NULL DEFAULT 1, "
            "created_at TEXT NOT NULL, "
            "last_login_at TEXT)"
        )
        conn.execute(
            "INSERT INTO users(id,username,password_hash,role,display_name,active,created_at,last_login_at) "
            "SELECT id,username,password_hash,role,display_name,active,created_at,last_login_at "
            "FROM users_legacy"
        )
        conn.execute("DROP TABLE users_legacy")
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA legacy_alter_table=OFF")
        conn.execute("PRAGMA foreign_keys=ON")


# 旧权限点 -> 新权限点（菜单 endpoint）映射，用于一次性数据库迁移
_LEGACY_PERM_MAP = {
    "admin": ["admin"],                      # 超级权限标记
    "front": ["front.pickups", "front.import_excel"],
    "printer": ["print.print_list"],
}


def _ensure_roles(conn):
    """内置角色只补缺，不覆盖管理员在角色管理里对自定义角色的改动。"""
    for key, (label, perms) in BUILTIN_ROLES.items():
        conn.execute(
            "INSERT OR IGNORE INTO roles(key,label,perms,is_builtin,created_at,updated_at) "
            "VALUES(?,?,?,1,?,?)",
            (key, label, json.dumps(perms, ensure_ascii=False), now(), now()),
        )
    conn.commit()


def _migrate_role_perms(conn):
    """把角色权限点从旧粗粒度 key 迁移为导航 endpoint。

    - 内置角色每次启动都以 BUILTIN_ROLES 为准同步（新增菜单后管理员仍全量）。
    - 自定义角色把旧 key 展开为新权限点，已是新权限点的保留。
    """
    for key, (label, perms) in BUILTIN_ROLES.items():
        conn.execute(
            "UPDATE roles SET label=?, perms=?, is_builtin=1 WHERE key=?",
            (label, json.dumps(perms, ensure_ascii=False), key),
        )
    try:
        from .nav import collect_permissions
        valid = {k for k, _ in collect_permissions()}
    except Exception:
        valid = set()
    for r in conn.execute("SELECT key, perms, is_builtin FROM roles").fetchall():
        if r["is_builtin"]:
            continue
        try:
            old = json.loads(r["perms"] or "[]")
        except (ValueError, TypeError):
            old = []
        new = []
        for p in old:
            if p in _LEGACY_PERM_MAP:
                candidates = _LEGACY_PERM_MAP[p]
            elif p == "admin" or p in valid or p.startswith(("front.", "print.", "admin.")):
                candidates = [p]
            else:
                candidates = []
            for np in candidates:
                if np not in new:
                    new.append(np)
        conn.execute("UPDATE roles SET perms=? WHERE key=?",
                     (json.dumps(new, ensure_ascii=False), r["key"]))
    conn.commit()


def _ensure_columns(conn):
    """老库补列：CREATE TABLE IF NOT EXISTS 不会给已存在的表加新列。

    - eir_records.remark_snapshot：起租号批次备注的快照（2026-11 新增）
    """
    def cols(table):
        return {r["name"] for r in conn.execute("PRAGMA table_info(%s)" % table).fetchall()}

    if "remark_snapshot" not in cols("eir_records"):
        conn.execute("ALTER TABLE eir_records ADD COLUMN remark_snapshot TEXT")
        conn.commit()


def init_db():
    os.makedirs(config.DATA_DIR, exist_ok=True)
    conn = connect()
    with open(config.SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    _ensure_columns(conn)
    _migrate_users_role(conn)
    _ensure_roles(conn)
    _migrate_role_perms(conn)
    for k, v in DEFAULT_SETTINGS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings(key,value,updated_at) VALUES(?,?,?)",
            (k, v, now()),
        )
    conn.commit()
    conn.close()


@contextmanager
def immediate(db=None):
    """写事务：BEGIN IMMEDIATE 串行化写者，防超卖。"""
    own = db is None
    conn = db or connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if own:
            conn.close()


def get_setting(key, conn=None, default=""):
    c = conn or get_db()
    row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row and row["value"] is not None else default


def set_setting(key, value, conn=None):
    c = conn or get_db()
    c.execute(
        "INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, str(value), now()),
    )


def backup_db(reason=""):
    """时间戳备份，不删除旧备份。"""
    if not os.path.exists(config.DB_PATH):
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = os.path.join(config.BACKUP_DIR, "eir_%s_%s.db" % (stamp, reason or "manual"))
    shutil.copy2(config.DB_PATH, dst)
    return dst
