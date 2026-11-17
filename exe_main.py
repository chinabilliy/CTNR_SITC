# -*- coding: utf-8 -*-
"""短租箱 EIR 系统 —— 免安装 exe 入口。

双击启动后用浏览器访问 http://localhost:8888
可选参数:
  --port=9000     指定端口（默认 8888，被占用时自动顺延）
  --no-browser    不自动打开浏览器（服务器/后台运行用）
  --reset-admin   把 admin 密码重置为 admin123（忘记密码时用）
  --import-excel  导入同目录下的「宁波FREEUSE提箱.xlsx」初始数据（仅空库生效）
"""
import os
import shutil
import socket
import sys
import threading
import time
import traceback


def _app_dir():
    """exe 所在目录（源码运行时为脚本目录）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _parse_port(argv):
    port = int(os.environ.get("PORT") or 8888)
    for i, arg in enumerate(argv):
        if arg.startswith("--port="):
            port = int(arg.split("=", 1)[1])
        elif arg == "--port" and i + 1 < len(argv):
            port = int(argv[i + 1])
    return port


def _port_in_use(port, host="127.0.0.1"):
    """用 connect 探测，避免 TIME_WAIT 的 bind 误判。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.35)
    try:
        return s.connect_ex((host, port)) == 0
    finally:
        s.close()


def _pick_port(preferred):
    for p in range(preferred, preferred + 10):
        if not _port_in_use(p):
            return p
    return None


def _lan_ips():
    ips = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
            s.close()
        except Exception:
            pass
    return ips


def _prepare_first_run():
    """首次运行：复制模板表格、示例 Excel，并建立默认账号。"""
    from app import config

    # 模板 xlsx（导入模板 / 示例）随包分发，复制到可写目录
    if os.path.isdir(config.SEED_EXCEL_DIR):
        for name in os.listdir(config.SEED_EXCEL_DIR):
            if not name.lower().endswith(".xlsx"):
                continue
            dst = os.path.join(config.EXCEL_TEMPLATE_DIR, name)
            if not os.path.exists(dst):
                try:
                    shutil.copy2(os.path.join(config.SEED_EXCEL_DIR, name), dst)
                except Exception:
                    pass

    if os.path.exists(config.SEED_SOURCE_EXCEL) and not os.path.exists(config.SOURCE_EXCEL):
        try:
            shutil.copy2(config.SEED_SOURCE_EXCEL, config.SOURCE_EXCEL)
        except Exception:
            pass

    # 默认账号（已存在则跳过，幂等）
    from app.seed import seed_users
    seed_users()


def _reset_admin():
    from app.db import get_db, now
    from app.auth import hash_pwd
    db = get_db()
    row = db.execute("SELECT id FROM users WHERE username='admin'").fetchone()
    if row:
        db.execute("UPDATE users SET password_hash=?, active=1 WHERE id=?",
                   (hash_pwd("admin123"), row["id"]))
        print("  已重置 admin 密码为 admin123")
    else:
        db.execute(
            "INSERT INTO users(username,password_hash,role,display_name,active,created_at) "
            "VALUES('admin',?,'admin','系统管理员',1,?)",
            (hash_pwd("admin123"), now()),
        )
        print("  已重建 admin 账号，密码 admin123")
    db.commit()


def _open_browser_later(url, delay=1.5):
    def _run():
        time.sleep(delay)
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


def _pause_if_needed():
    """双击运行时出错，保持窗口不闪退。"""
    if getattr(sys, "frozen", False) and sys.stdin and sys.stdin.isatty():
        try:
            input("\n按回车键退出...")
        except Exception:
            pass


def main():
    # 控制台：行缓冲（中文由 Windows 控制台直接渲染）
    # 重定向到文件：改用 UTF-8，避免记事本打开是乱码
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.isatty():
                stream.reconfigure(line_buffering=True, errors="replace")
            else:
                stream.reconfigure(encoding="utf-8", line_buffering=True, errors="replace")
        except Exception:
            pass

    base = _app_dir()
    os.chdir(base)

    argv = sys.argv[1:]
    preferred = _parse_port(argv)
    open_browser = "--no-browser" not in argv

    print("=" * 60)
    print("  短租箱 EIR 生成系统")
    print("  数据目录: %s" % os.path.join(base, "data"))
    print("=" * 60)

    try:
        from app import create_app
        from app import config

        app = create_app()
        with app.app_context():
            _prepare_first_run()
            if "--import-excel" in argv:
                from app.seed import seed_from_excel
                if os.path.exists(config.SOURCE_EXCEL):
                    seed_from_excel(config.SOURCE_EXCEL)
                else:
                    print("  [提示] 未找到 %s，跳过初始数据导入" % config.SOURCE_EXCEL)
            if "--reset-admin" in argv:
                _reset_admin()

        port = _pick_port(preferred)
        if port is None:
            print("  [错误] 端口 %d 起的 10 个端口都被占用了，请用 --port=9000 指定其它端口" % preferred)
            _pause_if_needed()
            return 1
        if port != preferred:
            print("  [提示] 端口 %d 已被占用，自动改用 %d" % (preferred, port))

        print("")
        print("  本机访问:   http://localhost:%d" % port)
        for ip in _lan_ips():
            print("  局域网访问: http://%s:%d" % (ip, port))
        print("")
        print("  默认账号:   admin/admin123（管理员）")
        print("              front/front123（前台）  print/print123（打印员）")
        print("")
        print("  关闭本窗口即停止服务，按 Ctrl+C 也可停止。")
        print("=" * 60)
        print("")

        if open_browser:
            _open_browser_later("http://localhost:%d" % port)

        from waitress import serve
        serve(app, host="0.0.0.0", port=port, threads=8, ident="ShortLeaseEIR")
        return 0
    except KeyboardInterrupt:
        print("\n服务已停止。")
        return 0
    except Exception:
        print("\n[启动失败] 详细信息如下：\n")
        traceback.print_exc()
        print("\n常见原因：")
        print("  1) exe 所在目录没有写入权限 —— 请放到 D 盘或桌面等可写目录")
        print("  2) 杀毒软件拦截 —— 将本程序加入白名单")
        print("  3) 端口被防火墙拦截 —— 放行对应端口")
        _pause_if_needed()
        return 1


if __name__ == "__main__":
    sys.exit(main())
