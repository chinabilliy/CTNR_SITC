#!/usr/bin/env bash
# 短租箱 EIR 生成系统 - Linux / macOS 启动脚本
set -e
cd "$(dirname "$0")"

PORT="${PORT:-8888}"

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PY=python3
  elif command -v python >/dev/null 2>&1; then
    PY=python
  else
    echo "ERROR: python3/python not found. Please install Python 3.9+"
    exit 1
  fi
fi

echo "[1/2] Checking dependencies..."
if ! $PY -m pip install -q --disable-pip-version-check -r requirements.txt; then
  echo "WARN: dependency install failed (offline?)."
  echo "      Please install manually: $PY -m pip install flask waitress openpyxl python-docx"
fi

echo "[2/2] Starting server on http://0.0.0.0:${PORT}"
exec $PY run.py --serve --port="${PORT}"
