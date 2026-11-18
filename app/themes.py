# -*- coding: utf-8 -*-
"""UI 主题注册表 —— 主题的唯一元数据来源。

themes.css 定义各主题的 CSS 变量（html[data-theme=key]）；
本模块提供 key/名称/预览色，供后台设置页渲染与校验。
新增主题：在 themes.css 加一组变量 + 在这里加一条 THEMES 记录即可，
业务代码无需改动。
"""

THEMES = [
    {"key": "default", "label": "蓝白（默认）",
     "side": "#1f2d3d", "page": "#f5f6f8", "primary": "#1a63c9"},
    {"key": "ocean", "label": "海洋绿",
     "side": "#123c33", "page": "#f2f7f5", "primary": "#0e7a5f"},
    {"key": "dark", "label": "暗夜",
     "side": "#10141b", "page": "#14181f", "primary": "#4c8dff"},
    {"key": "sunset", "label": "暖橙",
     "side": "#3d2a1c", "page": "#faf6f1", "primary": "#c2571b"},
]

DEFAULT_THEME = "default"
VALID_KEYS = {t["key"] for t in THEMES}


def normalize(key):
    """非法/空值一律回落到默认主题，避免页面拿到不存在的 data-theme。"""
    return key if key in VALID_KEYS else DEFAULT_THEME
