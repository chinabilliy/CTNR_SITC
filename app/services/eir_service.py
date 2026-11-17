# -*- coding: utf-8 -*-
"""EIR 批量生成：流水号、快照、图片路径。"""
import os
from datetime import datetime
from .. import config
from ..db import get_setting, set_setting, now


class SeqConflict(Exception):
    pass


def next_eir_no(conn):
    today = datetime.now().strftime("%Y%m%d")
    cur_date = get_setting("eir_seq_date", conn, "")
    if cur_date != today:
        set_setting("eir_seq_date", today, conn)
        set_setting("eir_seq", "0", conn)
        cur_date = today
    prefix = get_setting("eir_no_prefix", conn, "EIR") or "EIR"
    seq = int(get_setting("eir_seq", conn, "0")) + 1
    set_setting("eir_seq", str(seq), conn)
    return "%s%s-%04d" % (prefix, cur_date, seq)


def _release_image(conn, batch_id, yard_key):
    b = conn.execute("SELECT release_image_path FROM lease_batches WHERE id=?", (batch_id,)).fetchone()
    if b and b["release_image_path"]:
        return b["release_image_path"]
    # 新堆场不在 YARD_TEMPLATE_KEYS 里时 template_key 为空，兜底到默认图，
    # 避免拼出 /static/eir_assets/_template.png（不存在）导致打印时不显示。
    key = yard_key or "tianxiang"
    default = "/static/eir_assets/%s_template.png" % key
    if not os.path.exists(os.path.join(config.EIR_ASSET_DIR, "%s_template.png" % key)):
        default = "/static/eir_assets/tianxiang_template.png"
    return default


def generate_for_plan(conn, pickup, plan):
    """按拆分计划生成 EIR：plan=[(batch_id, take), ...]，数量=sum(take)。"""
    yard = conn.execute("SELECT * FROM yards WHERE id=?", (pickup["yard_id"],)).fetchone()
    created = []
    for batch_id, take in plan:
        batch = conn.execute("SELECT * FROM lease_batches WHERE id=?", (batch_id,)).fetchone()
        img = _release_image(conn, batch_id, yard["template_key"])
        for _ in range(take):
            eir_no = next_eir_no(conn)
            cur = conn.execute(
                "INSERT INTO eir_records(eir_no,pickup_id,batch_id,"
                "yard_name_snapshot,yard_address_snapshot,yard_phone_snapshot,work_hours_snapshot,"
                "vessel,voyage,bl_no,container_type,lease_no_snapshot,image_path_snapshot,"
                "print_count,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,0,?)",
                (eir_no, pickup["id"], batch_id,
                 yard["full_name"], yard["address"], yard["phone"], yard["work_hours"],
                 pickup["vessel"], pickup["voyage"], pickup["bl_no"], pickup["container_type"],
                 batch["lease_no"], img, now()),
            )
            created.append(cur.lastrowid)
    return created


def eirs_for_pickup(pickup_id, conn):
    return conn.execute(
        "SELECT * FROM eir_records WHERE pickup_id=? ORDER BY id", (pickup_id,)
    ).fetchall()
