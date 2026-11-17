# -*- coding: utf-8 -*-
"""侧边栏三级菜单定义与渲染上下文。

【权限点唯一来源】本文件的 MENU 叶子节点即「权限点」：
  - 权限点 key = 叶子节点的 endpoint（如 front.pickups / admin.yards）
  - 权限点名称 = 叶子节点的 label（如 提箱登记 / 堆场信息）
角色管理页面的勾选项、角色保存的白名单、导航可见性，全部从此处派生。
因此：新增/删除/改名一个三级菜单项，权限点会自动同步，无需改其它文件。

扩展方式：在 MENU 里追加/修改节点即可，无需改模板。
节点约定：
  - label：显示文字（同时作为权限点名称）
  - endpoint：Flask 端点；叶子节点的 endpoint 即权限点 key
  - perms：显式指定的权限点元组；叶子不写时默认用自身 endpoint
  - match：额外算作该叶子「当前项」的端点元组（如新增/编辑页）
  - children：子节点列表；有 children 的节点为分组（分组本身不是权限点）
"""
from flask import url_for

MENU = [
    {
        "label": "箱管模块",
        "children": [
            {
                "label": "短租箱EIR",
                "children": [
                    {"label": "提箱登记", "endpoint": "front.pickups",
                     "match": ("front.pickup_add", "front.pickup_edit", "front.pickup_delete")},
                    {"label": "Excel 导入", "endpoint": "front.import_excel",
                     "match": ("front.download_template",)},
                    {"label": "EIR 打印", "endpoint": "print.print_list",
                     "match": ("print.print_sheet", "print.print_mark", "print.print_help")},
                ],
            },
        ],
    },
    {
        "label": "后台管理",
        "children": [
            {
                "label": "短租箱EIR管理",
                "children": [
                    {"label": "工作台", "endpoint": "admin.dashboard"},
                    {"label": "放箱确认", "endpoint": "admin.release_list",
                     "match": ("admin.release_confirm", "admin.release_reset",
                               "admin.release_reset_print")},
                    {"label": "起租号批次与库存", "endpoint": "admin.batches",
                     "match": ("admin.batch_save", "admin.batch_stock_update",
                               "admin.batch_image", "admin.batch_delete")},
                    {"label": "堆场信息", "endpoint": "admin.yards",
                     "match": ("admin.yard_save", "admin.yard_delete")},
                    {"label": "角色管理", "endpoint": "admin.roles",
                     "match": ("admin.role_save", "admin.role_delete")},
                    {"label": "用户管理", "endpoint": "admin.users",
                     "match": ("admin.user_save",)},
                    {"label": "系统设置", "endpoint": "admin.settings"},
                    {"label": "导出 Excel", "endpoint": "admin.export_excel"},
                ],
            },
        ],
    },
]


def _children(node):
    return node.get("children") or []


def _leaf_perm(node):
    """叶子节点的权限点 key：显式 perms 优先，否则用自身 endpoint。"""
    perms = node.get("perms")
    if perms:
        return perms[0]
    return node.get("endpoint")


def _walk_leaves(nodes):
    for node in nodes:
        kids = _children(node)
        if kids:
            for leaf in _walk_leaves(kids):
                yield leaf
        elif node.get("endpoint"):
            yield node


def collect_permissions():
    """从导航树派生权限点清单，按菜单顺序返回 [(key, label), ...]。

    这是角色管理页面与角色保存校验的唯一数据来源。
    """
    out, seen = [], set()
    for leaf in _walk_leaves(MENU):
        key = _leaf_perm(leaf)
        if key and key not in seen:
            seen.add(key)
            out.append((key, leaf["label"]))
    return out


def permission_labels():
    return {k: label for k, label in collect_permissions()}


def permission_groups():
    """按导航层级组织权限点，用于角色管理页分组展示。

    返回 [{"label": 一级, "groups": [{"label": 二级, "perms": [(key, label), ...]}]}, ...]。
    仅保留含权限点的分支；叶子权限点用其所属二级的 label。
    """
    out = []
    seen = set()
    for l1 in MENU:
        groups = []
        for l2 in _children(l1):
            perms = []
            for leaf in _walk_leaves([l2]):
                key = _leaf_perm(leaf)
                if key and key not in seen:
                    seen.add(key)
                    perms.append((key, leaf["label"]))
            if perms:
                groups.append({"label": l2["label"], "perms": perms})
        if groups:
            out.append({"label": l1["label"], "groups": groups})
    return out


def endpoint_permissions():
    """返回 {endpoint: perm_key}，把每个端点（含 match 子页）映射到叶子权限点。"""
    mapping = {}
    for leaf in _walk_leaves(MENU):
        key = _leaf_perm(leaf)
        if not key:
            continue
        mapping[leaf["endpoint"]] = key
        for ep in leaf.get("match", ()):
            mapping[ep] = key
    return mapping


def _visible(node, perms):
    kids = _children(node)
    if kids:
        return any(_visible(c, perms) for c in kids)
    key = _leaf_perm(node)
    # 没有显式权限点的叶子对所有登录用户可见
    return True if not key else (key in perms)


def _decorate(node, perms, current):
    out = {"label": node["label"]}
    if "endpoint" in node:
        try:
            out["url"] = url_for(node["endpoint"])
        except Exception:
            out["url"] = "#"  # 配置端点写错时不拖垮整页
        keys = (node["endpoint"],) + tuple(node.get("match", ()))
        out["active"] = current in keys
    kids = _children(node)
    if kids:
        kept = [_decorate(c, perms, current) for c in kids if _visible(c, perms)]
        out["children"] = kept
        out["active"] = any(c.get("active") for c in kept)
    return out


def build_menu(perms, current):
    """返回按权限点过滤、带 active 标记的菜单树。"""
    return [_decorate(n, perms, current) for n in MENU if _visible(n, perms)]
