# -*- coding: utf-8 -*-
"""把短租箱 EIR 系统打包成免安装单文件 exe。

用法（在项目根目录）:
    python build_exe.py

产物: dist/短租箱EIR系统.exe
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
NAME = "短租箱EIR系统"
WORK = os.path.join(ROOT, "work", "exe-build")
DIST = os.path.join(ROOT, "dist", "exe")

# 只打运行必需的数据文件
DATAS = [
    (os.path.join(ROOT, "app", "templates"), "app/templates"),
    (os.path.join(ROOT, "app", "static"), "app/static"),
    (os.path.join(ROOT, "app", "excel_templates"), "app/excel_templates"),
    (os.path.join(ROOT, "app", "schema.sql"), "app"),
    (os.path.join(ROOT, "宁波FREEUSE提箱.xlsx"), "."),
]

HIDDEN = [
    "app.routes.auth_routes",
    "app.routes.front_routes",
    "app.routes.admin_routes",
    "app.routes.print_routes",
    "app.services.allocation",
    "app.services.eir_service",
    "app.services.excel_io",
    "app.services.print_service",
    "waitress",
    "openpyxl",
]

EXCLUDES = [
    "tkinter", "numpy", "pandas", "matplotlib", "scipy", "PIL",
    "PyQt5", "PySide2", "PyQt6", "IPython", "notebook", "pytest",
    "sqlalchemy", "boto3", "botocore", "sphinx", "docutils",
]


def main():
    for d in (WORK, DIST):
        os.makedirs(d, exist_ok=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--console",
        "--name", NAME,
        "--distpath", DIST,
        "--workpath", WORK,
        "--specpath", WORK,
        "--log-level", "WARN",
    ]
    for src, dst in DATAS:
        if not os.path.exists(src):
            raise SystemExit("缺少打包资源: %s" % src)
        cmd += ["--add-data", "%s;%s" % (src, dst)]
    for m in HIDDEN:
        cmd += ["--hidden-import", m]
    for m in EXCLUDES:
        cmd += ["--exclude-module", m]

    cmd.append(os.path.join(ROOT, "exe_main.py"))

    print("开始打包，约需 1-3 分钟 ...")
    subprocess.run(cmd, cwd=ROOT, check=True)

    exe = os.path.join(DIST, NAME + ".exe")
    if not os.path.exists(exe):
        raise SystemExit("打包失败：未生成 %s" % exe)
    size = os.path.getsize(exe) / 1024 / 1024
    print("\n完成: %s (%.1f MB)" % (exe, size))

    # 附一份说明到产物目录
    guide = os.path.join(ROOT, "exe使用说明.txt")
    if os.path.exists(guide):
        shutil.copy2(guide, os.path.join(DIST, "exe使用说明.txt"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
