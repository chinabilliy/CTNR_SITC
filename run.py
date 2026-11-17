# -*- coding: utf-8 -*-
"""短租箱 EIR 生成系统启动入口。

开发运行:  python run.py
内网常驻:  python run.py --serve   (Waitress, 0.0.0.0:8888)
初始化管理员: python -m app.seed
首次导入 Excel: python -m app.seed --import-excel
"""
import sys
from app import create_app


def main():
    app = create_app()
    if "--serve" in sys.argv:
        from waitress import serve
        host = "0.0.0.0"
        port = 8888
        for arg in sys.argv:
            if arg.startswith("--port="):
                port = int(arg.split("=", 1)[1])
        print("短租箱 EIR 系统启动: http://%s:%d" % (host, port), flush=True)
        serve(app, host=host, port=port, threads=8)
    else:
        print("短租箱 EIR 系统启动: http://127.0.0.1:5000", flush=True)
        app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)


if __name__ == "__main__":
    main()
