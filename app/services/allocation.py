# -*- coding: utf-8 -*-
"""自动放箱分配：箱型+堆场筛选、优先级排序、允许拆单、事务扣减。"""
from ..db import get_setting, now


class AllocError(Exception):
    pass


class AlreadyReleased(Exception):
    pass


def candidates(pickup, conn):
    return conn.execute(
        "SELECT b.id, b.lease_no, b.priority, s.available "
        "FROM lease_batches b JOIN batch_stock s ON s.batch_id=b.id "
        "WHERE b.yard_id=? AND b.status='active' AND s.container_type=? AND s.available>0 "
        "ORDER BY b.priority ASC, b.id ASC",
        (pickup["yard_id"], pickup["container_type"]),
    ).fetchall()


def _check_batch(batch_id, pickup, conn, yard_id):
    b = conn.execute(
        "SELECT b.*, s.available FROM lease_batches b "
        "LEFT JOIN batch_stock s ON s.batch_id=b.id AND s.container_type=? "
        "WHERE b.id=?",
        (pickup["container_type"], batch_id),
    ).fetchone()
    if not b or b["yard_id"] != yard_id:
        raise AllocError("指定起租号不属于该堆场或不存在")
    if b["status"] != "active":
        raise AllocError("该批次已关闭")
    if (b["available"] or 0) < pickup["quantity"]:
        raise AllocError("该批次库存不足（需 %d，余 %d）" % (pickup["quantity"], b["available"] or 0))
    return b


def build_plan(pickup, conn, manual_batch_id=None, release_no=None):
    """返回 [(batch_id, take), ...]。"""
    yard_id = pickup["yard_id"]
    need = pickup["quantity"]

    # 1) 人工改派（最高优先）
    if manual_batch_id is not None:
        _check_batch(manual_batch_id, pickup, conn, yard_id)
        return [(int(manual_batch_id), need)]

    # 2) 前台指定起租号（且后台未改派）
    if release_no:
        b = conn.execute(
            "SELECT id FROM lease_batches WHERE yard_id=? AND lease_no=?",
            (yard_id, release_no),
        ).fetchone()
        if not b:
            raise AllocError("指定起租号 %s 不属于该堆场或不存在" % release_no)
        _check_batch(b["id"], pickup, conn, yard_id)
        return [(b["id"], need)]

    # 3) 自动匹配：箱型+堆场 → 优先级升序
    cands = candidates(pickup, conn)
    if not cands:
        raise AllocError("无可用批次（箱型 %s，堆场 ID %s）" % (pickup["container_type"], yard_id))

    # 优先找单个批次能满足的
    for c in cands:
        if c["available"] >= need:
            return [(c["id"], need)]

    # 允许拆单
    if get_setting("allow_split", conn, "1") == "1":
        plan, remaining = [], need
        for c in cands:
            take = min(remaining, c["available"])
            if take <= 0:
                continue
            plan.append((c["id"], take))
            remaining -= take
            if remaining == 0:
                break
        if remaining > 0:
            raise AllocError("所有可用批次库存合计仍不足，尚缺 %d 箱" % remaining)
        return plan

    raise AllocError("无单一批次库存足够（可在设置开启拆单）")


def deduct(conn, plan, container_type):
    """事务内扣减；rowcount!=1 视为冲突回滚。"""
    for bid, take in plan:
        cur = conn.execute(
            "UPDATE batch_stock SET available=available-?, updated_at=? "
            "WHERE batch_id=? AND container_type=? AND available>=?",
            (take, now(), bid, container_type, take),
        )
        if cur.rowcount != 1:
            raise AllocError("库存冲突，放箱已回滚")


def allocate_one(pickup, conn, user_id=None, manual_batch_id=None, respect_requested=True):
    """完整的单条放箱：校验状态→生成计划→扣库存→返回计划。调用方负责在外层事务内提交。

    respect_requested=False：后台改派了堆场，前台登记的「指定起租号」只作参考，
    不再参与分配，改按新堆场自动匹配（或服从人工改派批次）。
    """
    if pickup["status"] != "pending":
        raise AlreadyReleased("该登记已放箱")
    release_no = pickup["requested_lease_no"] if respect_requested else None
    plan = build_plan(pickup, conn, manual_batch_id=manual_batch_id, release_no=release_no)
    deduct(conn, plan, pickup["container_type"])
    conn.execute(
        "UPDATE pickups SET status='released', confirmed_by=?, confirmed_at=?, updated_at=? WHERE id=?",
        (user_id, now(), now(), pickup["id"]),
    )
    return plan
