# -*- coding: utf-8 -*-
"""三表 Excel 导入 / 导出。类型归一，表头行差异，冗余列忽略，首次建库存。"""
import os
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, Alignment
from .. import config
from ..db import now, immediate

CONTAINER_TYPES = config.CONTAINER_TYPES


# ---------- 通用归一 ----------
def norm_text(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def norm_lease(v):
    """起租号统一文本：687777(int) -> '687777'; G0050288 -> 'G0050288'。"""
    return norm_text(v)


def norm_int(v):
    if v is None or v == "":
        return 0
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip()
    try:
        return int(float(s))
    except ValueError:
        raise ValueError("非整数: %r" % v)


def _header_map(ws, row_no):
    return {norm_text(ws.cell(row_no, c).value): c for c in range(1, ws.max_column + 1)
            if norm_text(ws.cell(row_no, c).value)}


def _sheet(wb, name):
    if name not in wb.sheetnames:
        raise ValueError("缺少工作表: %s" % name)
    return wb[name]


# ---------- 堆场信息 ----------
def import_yards(path, db=None, commit=True, owner_id=None):
    own = db is None
    db = db or _connect()
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = _sheet(wb, "堆场信息")
    hm = _header_map(ws, 1)
    need = ("堆场", "简称", "堆场地址", "联系电话", "作业时间")
    for k in need:
        if k not in hm:
            raise ValueError("堆场信息表头缺少: %s" % k)
    errors, rows = [], []
    for r in range(2, ws.max_row + 1):
        def g(k):
            return norm_text(ws.cell(r, hm[k]).value) if k in hm else ""
        full, short = g("堆场"), g("简称")
        if not full and not short:
            continue
        if not full or not short:
            errors.append((r, "堆场全称或简称缺失"))
            continue
        rows.append((full, short, g("堆场地址"), g("联系电话"), g("作业时间")))
    if errors:
        return {"ok": False, "errors": errors}
    ts = now()
    n = 0
    for full, short, addr, phone, hours in rows:
        key = config.YARD_TEMPLATE_KEYS.get(short, "")
        exists = db.execute("SELECT id FROM yards WHERE short_name=?", (short,)).fetchone()
        if exists:
            db.execute(
                "UPDATE yards SET full_name=?,address=?,phone=?,work_hours=?,template_key=?,updated_at=? WHERE id=?",
                (full, addr, phone, hours, key or _existing_template(db, short), ts, exists["id"]),
            )
        else:
            db.execute(
                "INSERT INTO yards(full_name,short_name,address,phone,work_hours,template_key,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (full, short, addr, phone, hours, key, ts, ts),
            )
        n += 1
    if commit:
        db.commit()
    if own:
        db.close()
    return {"ok": True, "inserted": n, "updated": n}


def _existing_template(db, short):
    row = db.execute("SELECT template_key FROM yards WHERE short_name=?", (short,)).fetchone()
    return row["template_key"] if row else ""


# ---------- 起租号登记 ----------
def import_batches(path, db=None, commit=True, owner_id=None):
    own = db is None
    db = db or _connect()
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = _sheet(wb, "起租号登记")
    hm = _header_map(ws, 1)
    errors, rows = [], []
    for r in range(2, ws.max_row + 1):
        def g(k):
            return ws.cell(r, hm[k]).value if k in hm else None
        short, lease = norm_text(g("简称")), norm_lease(g("起租号"))
        if not short and not lease:
            continue
        if not short or not lease:
            errors.append((r, "简称或起租号缺失"))
            continue
        yard = db.execute("SELECT id FROM yards WHERE short_name=?", (short,)).fetchone()
        if not yard:
            errors.append((r, "堆场简称未登记: %s" % short))
            continue
        stocks = {}
        for ct in CONTAINER_TYPES:
            if ct in hm:
                raw = g(ct)
                if raw is not None and norm_text(raw) != "":
                    try:
                        stocks[ct] = max(0, norm_int(raw))
                    except ValueError:
                        errors.append((r, "%s 数量非法" % ct))
        try:
            prio = norm_int(g("优先级")) if "优先级" in hm else 99
        except ValueError:
            prio = 99
        rows.append((yard["id"], lease, prio, norm_text(g("备注")), stocks))
    if errors:
        return {"ok": False, "errors": errors}
    ts = now()
    n_batch = n_stock = 0
    for yard_id, lease, prio, remark, stocks in rows:
        b = db.execute(
            "SELECT id FROM lease_batches WHERE yard_id=? AND lease_no=?", (yard_id, lease)
        ).fetchone()
        if b:
            # 重复导入：只更新优先级/备注/状态，不覆盖库存（用户决策）
            db.execute(
                "UPDATE lease_batches SET priority=?,remark=?,status='active',updated_at=? WHERE id=?",
                (prio, remark, ts, b["id"]),
            )
            bid = b["id"]
        else:
            cur = db.execute(
                "INSERT INTO lease_batches(yard_id,lease_no,priority,remark,status,created_at,updated_at) "
                "VALUES(?,?,?,?,'active',?,?)",
                (yard_id, lease, prio, remark, ts, ts),
            )
            bid = cur.lastrowid
            n_batch += 1
        for ct, qty in stocks.items():
            s = db.execute(
                "SELECT id FROM batch_stock WHERE batch_id=? AND container_type=?", (bid, ct)
            ).fetchone()
            if s:
                # 已存在的库存不被覆盖
                continue
            db.execute(
                "INSERT INTO batch_stock(batch_id,container_type,available,updated_at) VALUES(?,?,?,?)",
                (bid, ct, qty, ts),
            )
            n_stock += 1
    if commit:
        db.commit()
    if own:
        db.close()
    return {"ok": True, "batches": n_batch, "stock_rows": n_stock, "rows": len(rows)}


# ---------- 提箱登记 ----------
def import_pickups(path, db=None, commit=True, owner_id=None):
    own = db is None
    db = db or _connect()
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = _sheet(wb, "提箱登记")
    # 第1行标题，第2行表头
    if norm_text(ws.cell(1, 1).value) != "船名" and norm_text(ws.cell(2, 1).value) != "船名":
        # 兼容表头在第1行的情况
        header_row = 1 if norm_text(ws.cell(1, 1).value) == "船名" else 2
    else:
        header_row = 2
    hm = _header_map(ws, header_row)
    errors, rows = [], []
    for r in range(header_row + 1, ws.max_row + 1):
        def g(k):
            return ws.cell(r, hm[k]).value if k in hm else None
        vals = [ws.cell(r, c).value for c in range(1, ws.max_column + 1)]
        if not any(v is not None and norm_text(v) != "" for v in vals):
            continue
        bl = norm_text(g("提单号"))
        ctype = norm_text(g("箱型"))
        if not bl:
            errors.append((r, "提单号缺失"))
            continue
        if ctype not in CONTAINER_TYPES:
            errors.append((r, "箱型非法: %s" % (ctype or "空")))
            continue
        yard_short = norm_text(g("堆场"))
        yard = db.execute("SELECT id FROM yards WHERE short_name=?", (yard_short,)).fetchone()
        if not yard:
            errors.append((r, "堆场简称未登记: %s" % yard_short))
            continue
        try:
            qty = norm_int(g("数量"))
            if qty <= 0:
                raise ValueError()
        except ValueError:
            errors.append((r, "数量非法"))
            continue
        try:
            pcnt = norm_int(g("EIR打印次数"))
        except ValueError:
            pcnt = 0
        rows.append((norm_text(g("船名")), norm_text(g("航次")), bl, ctype, qty,
                     yard["id"], norm_lease(g("起租号")), pcnt))
    if errors:
        return {"ok": False, "errors": errors}
    ts = now()
    n = 0
    for vessel, voyage, bl, ct, qty, yard_id, lease, pcnt in rows:
        exists = db.execute("SELECT id FROM pickups WHERE bl_no=? AND container_type=?", (bl, ct)).fetchone()
        if exists:
            continue  # 重复导入跳过（用户决策：不覆盖）
        db.execute(
            "INSERT INTO pickups(vessel,voyage,bl_no,container_type,quantity,yard_id,"
            "requested_lease_no,eir_print_count,status,created_by,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,'pending',?,?,?)",
            (vessel, voyage, bl, ct, qty, yard_id, lease or None, pcnt, owner_id, ts, ts),
        )
        n += 1
    if commit:
        db.commit()
    if own:
        db.close()
    return {"ok": True, "inserted": n, "skipped": len(rows) - n}


def _connect():
    from ..db import connect
    return connect()


# ---------- 导出（另存新文件，不动源表） ----------
def export_workbook(path=None):
    """导出三表到新 xlsx，格式与源模板一致。"""
    from ..db import connect
    wb = openpyxl.Workbook()
    db = connect()

    ws = wb.active
    ws.title = "提箱登记"
    ws.append(["短租箱提箱登记"])
    ws.append(["船名", "航次", "提单号", "箱型", "数量", "堆场", "起租号", "EIR打印次数"])
    for row in db.execute(
        "SELECT p.*,y.short_name AS yard_short FROM pickups p JOIN yards y ON p.yard_id=y.id ORDER BY p.id"
    ):
        ws.append([row["vessel"], row["voyage"], row["bl_no"], row["container_type"],
                   row["quantity"], row["yard_short"], row["requested_lease_no"] or "",
                   row["eir_print_count"]])

    ws2 = wb.create_sheet("起租号登记")
    ws2.append(["简称", "起租号", "20GP", "40GP", "40HC", "优先级", "备注"])
    for b in db.execute(
        "SELECT b.*,y.short_name AS yard_short FROM lease_batches b JOIN yards y ON b.yard_id=y.id ORDER BY b.id"
    ):
        stocks = {s["container_type"]: s["available"] for s in db.execute(
            "SELECT container_type,available FROM batch_stock WHERE batch_id=?", (b["id"],))}
        ws2.append([b["yard_short"], b["lease_no"], stocks.get("20GP", ""), stocks.get("40GP", ""),
                    stocks.get("40HC", ""), b["priority"], b["remark"] or ""])

    ws3 = wb.create_sheet("堆场信息")
    ws3.append(["堆场", "简称", "堆场地址", "联系电话", "作业时间"])
    for y in db.execute("SELECT * FROM yards ORDER BY id"):
        ws3.append([y["full_name"], y["short_name"], y["address"], y["phone"] or "", y["work_hours"] or ""])

    db.close()
    for sheet in (ws, ws2, ws3):
        for cell in sheet[1] if sheet is not ws else sheet[2]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center")
        for col in sheet.columns:
            width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
            sheet.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 60)

    if path is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = os.path.join(config.EXCEL_TEMPLATE_DIR, "宁波FREEUSE提箱_导出_%s.xlsx" % stamp)
    wb.save(path)
    return path


def make_blank_import_templates():
    """生成三份空白导入模板（供用户下载）。"""
    specs = {
        "堆场信息_导入模板.xlsx": ["堆场", "简称", "堆场地址", "联系电话", "作业时间"],
        "起租号登记_导入模板.xlsx": ["简称", "起租号", "20GP", "40GP", "40HC", "优先级", "备注"],
    }
    for fn, headers in specs.items():
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = fn.replace("_导入模板.xlsx", "")
        ws.append(headers)
        for c in ws[1]:
            c.font = Font(bold=True)
        ws.column_dimensions["A"].width = 32
        wb.save(os.path.join(config.EXCEL_TEMPLATE_DIR, fn))

    # 提箱登记模板（标题行 + 表头行）
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "提箱登记"
    ws.append(["短租箱提箱登记"])
    ws.append(["船名", "航次", "提单号", "箱型", "数量", "堆场", "起租号", "EIR打印次数"])
    for c in ws[2]:
        c.font = Font(bold=True)
    wb.save(os.path.join(config.EXCEL_TEMPLATE_DIR, "提箱登记_导入模板.xlsx"))
