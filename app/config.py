# -*- coding: utf-8 -*-
"""路径与全局配置。

两套目录概念：
  * APP_DIR     —— 只读资源（templates / static / schema.sql / eir_assets）
                  源码运行 = 项目/app；exe 运行 = 解包临时目录/app
  * DATA_ROOT   —— 可写数据（data / uploads / backups / excel_templates）
                  源码运行 = 项目/app（保持历史布局）；exe 运行 = exe 所在目录

打包成单文件 exe 后数据必须落在 exe 旁边，不能写进 _MEIPASS（退出即被清理）。
"""
import os
import sys

FROZEN = bool(getattr(sys, "frozen", False))

if FROZEN:
    RUNTIME_DIR = os.path.dirname(os.path.abspath(sys.executable))
    RESOURCE_DIR = getattr(sys, "_MEIPASS", RUNTIME_DIR)
    APP_DIR = os.path.join(RESOURCE_DIR, "app")
    DATA_ROOT = RUNTIME_DIR
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))        # .../app
    RUNTIME_DIR = os.path.dirname(APP_DIR)                      # 项目根
    RESOURCE_DIR = RUNTIME_DIR
    DATA_ROOT = APP_DIR

BASE_DIR = APP_DIR                                              # 兼容旧引用
PROJECT_DIR = RUNTIME_DIR                                       # 兼容旧引用

SOURCE_EXCEL = os.path.join(RUNTIME_DIR, "宁波FREEUSE提箱.xlsx")
DATA_DIR = os.path.join(DATA_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "eir.db")
SCHEMA_PATH = os.path.join(APP_DIR, "schema.sql")
UPLOAD_ROOT = os.path.join(DATA_ROOT, "uploads")
UPLOAD_DIR = os.path.join(UPLOAD_ROOT, "release_notes")
EIR_ASSET_DIR = os.path.join(APP_DIR, "static", "eir_assets")
BACKUP_DIR = os.path.join(DATA_ROOT, "backups")
EXCEL_TEMPLATE_DIR = os.path.join(DATA_ROOT, "excel_templates")

# exe 首启时，把随包分发的模板 / 示例表格复制到可写目录
SEED_EXCEL_DIR = os.path.join(APP_DIR, "excel_templates")
SEED_SOURCE_EXCEL = os.path.join(RESOURCE_DIR, "宁波FREEUSE提箱.xlsx")

for _d in (DATA_DIR, UPLOAD_ROOT, UPLOAD_DIR, BACKUP_DIR, EXCEL_TEMPLATE_DIR):
    os.makedirs(_d, exist_ok=True)

SECRET_KEY = "sitc-shortlease-eir-2026-local-secret"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20MB 上传上限

YARD_TEMPLATE_KEYS = {
    "天翔": "tianxiang",
    "海盛通": "haishengtong",
    "珉钧": "minjun",
    "鑫润韩": "xinrunhan",
}
CONTAINER_TYPES = ("20GP", "40GP", "40HC")
