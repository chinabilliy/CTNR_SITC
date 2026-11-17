# -*- coding: utf-8 -*-
"""路径与全局配置。"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))          # .../app
PROJECT_DIR = os.path.dirname(BASE_DIR)                         # 项目根

SOURCE_EXCEL = os.path.join(PROJECT_DIR, "宁波FREEUSE提箱.xlsx")
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "eir.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads", "release_notes")
EIR_ASSET_DIR = os.path.join(BASE_DIR, "static", "eir_assets")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
EXCEL_TEMPLATE_DIR = os.path.join(BASE_DIR, "excel_templates")

for _d in (DATA_DIR, UPLOAD_DIR, BACKUP_DIR, EXCEL_TEMPLATE_DIR):
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
