# -*- coding: utf-8 -*-
"""打印筛选与次数累加。

注意：mark_printed 必须在调用方的 BEGIN IMMEDIATE 写事务内执行，
以保证「读 targets → UPDATE」原子化，避免并发下计数不一致。
"""
from ..db import now


def printable_by_bls(bl_nos, conn, include_printed=False):
    """按提单取可打印 EIR（已放箱）。include_printed=False 时只取未打印的。"""
    if not bl_nos:
        return []
    ph = ",".join("?" for _ in bl_nos)
    extra = "" if include_printed else " AND e.print_count=0"
    return conn.execute(
        "SELECT e.*, y.template_key FROM eir_records e "
        "JOIN pickups p ON p.id=e.pickup_id "
        "JOIN lease_batches b ON b.id=e.batch_id "
        "JOIN yards y ON y.id=b.yard_id "
        "WHERE p.bl_no IN (%s) AND p.status='released'%s "
        "ORDER BY p.bl_no, e.eir_no" % (ph, extra),
        tuple(bl_nos),
    ).fetchall()


def printable_by_bl(bl_no, conn, include_printed=False):
    return printable_by_bls([bl_no], conn, include_printed=include_printed)


def mark_printed(eir_ids, conn, allow_reprint=False):
    """点打印即累加：同一事务内更新 EIR 与提箱登记的打印次数。

    allow_reprint=False：仅 print_count=0 的 EIR 参与（原行为）。
    allow_reprint=True ：全部给定 id 参与（管理员开启重印）。
    pickups.eir_print_count 只按「确实被累加的 EIR」所属提单 +1，
    杜绝 EIR 未累加却给提单计数的旧 bug。
    """
    if not eir_ids:
        return 0
    ph = ",".join("?" for _ in eir_ids)
    extra = "" if allow_reprint else " AND print_count=0"

    targets = conn.execute(
        "SELECT id, pickup_id FROM eir_records WHERE id IN (%s)%s" % (ph, extra),
        tuple(eir_ids),
    ).fetchall()
    if not targets:
        return 0

    tph = ",".join("?" for _ in targets)
    cur = conn.execute(
        "UPDATE eir_records SET print_count=print_count+1, printed_at=? "
        "WHERE id IN (%s)" % tph,
        (now(),) + tuple(t["id"] for t in targets),
    )
    affected = cur.rowcount

    # 口径：一次打印动作，每个涉及的提单 +1（不是每张 EIR +1）
    for pickup_id in {t["pickup_id"] for t in targets}:
        conn.execute(
            "UPDATE pickups SET eir_print_count=eir_print_count+1, updated_at=? WHERE id=?",
            (now(), pickup_id),
        )
    return affected


def eirs_by_ids(ids, conn, only_unprinted=False):
    """按 id 取 EIR；only_unprinted=True 时过滤掉已打印的（防构造 URL 绕过重印）。"""
    if not ids:
        return []
    ph = ",".join("?" for _ in ids)
    extra = " AND e.print_count=0" if only_unprinted else ""
    return conn.execute(
        "SELECT e.*, y.template_key FROM eir_records e "
        "JOIN lease_batches b ON b.id=e.batch_id JOIN yards y ON y.id=b.yard_id "
        "WHERE e.id IN (%s)%s ORDER BY e.eir_no" % (ph, extra),
        tuple(ids),
    ).fetchall()
