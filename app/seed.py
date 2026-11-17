# -*- coding: utf-8 -*-
"""初始化管理员账号；可选从源 Excel 首次导入。"""
import sys
from . import create_app
from .db import get_db, now
from .auth import hash_pwd
from .services.excel_io import import_yards, import_batches, import_pickups


def seed_users():
    db = get_db()
    initial = [
        ("admin", "admin123", "admin", "系统管理员"),
        ("front", "front123", "front", "前台录入"),
        ("print", "print123", "printer", "打印员"),
    ]
    for username, pwd, role, disp in initial:
        if db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            continue
        db.execute(
            "INSERT INTO users(username,password_hash,role,display_name,active,created_at) "
            "VALUES(?,?,?,?,1,?)",
            (username, hash_pwd(pwd), role, disp, now()),
        )
    db.commit()


def seed_from_excel(path=None):
    from . import config
    path = path or config.SOURCE_EXCEL
    db = get_db()
    if db.execute("SELECT 1 FROM yards LIMIT 1").fetchone():
        print("主数据已存在，跳过 Excel 首次导入")
        return
    for fn in (import_yards, import_batches, import_pickups):
        res = fn(path, db=db, commit=True)
        print(fn.__name__, res)


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        seed_users()
        if "--import-excel" in sys.argv:
            seed_from_excel()
    print("seed done")
