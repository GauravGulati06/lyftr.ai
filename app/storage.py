from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite

from app.models import MessageIn


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


async def ensure_schema(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS messages ("
            "message_id TEXT PRIMARY KEY,"
            "from_msisdn TEXT NOT NULL,"
            "to_msisdn TEXT NOT NULL,"
            "ts TEXT NOT NULL,"
            "text TEXT,"
            "created_at TEXT NOT NULL"
            ")"
        )
        await db.commit()


async def check_db(db_path: str) -> bool:
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("SELECT 1")
            cur = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='messages'"
            )
            row = await cur.fetchone()
            return row is not None
    except Exception:
        return False


async def insert_message(db_path: str, msg: MessageIn) -> bool:
    created_at = _now_iso()
    async with aiosqlite.connect(db_path) as db:
        try:
            await db.execute(
                "INSERT INTO messages (message_id, from_msisdn, to_msisdn, ts, text, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    msg.message_id,
                    msg.from_msisdn,
                    msg.to_msisdn,
                    msg.ts,
                    msg.text,
                    created_at,
                ),
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def list_messages(
    db_path: str,
    limit: int,
    offset: int,
    from_msisdn: str | None,
    since: str | None,
    q: str | None,
) -> tuple[list[dict], int]:
    where: list[str] = []
    params: list[object] = []

    if from_msisdn:
        where.append("from_msisdn = ?")
        params.append(from_msisdn)

    if since:
        where.append("ts >= ?")
        params.append(since)

    if q:
        where.append("text LIKE ? COLLATE NOCASE")
        params.append(f"%{q}%")

    where_sql = "" if not where else " WHERE " + " AND ".join(where)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur_total = await db.execute(f"SELECT COUNT(*) AS c FROM messages{where_sql}", params)
        total_row = await cur_total.fetchone()
        total = int(total_row["c"]) if total_row else 0

        cur = await db.execute(
            f"SELECT message_id, from_msisdn, to_msisdn, ts, text FROM messages{where_sql} "
            "ORDER BY ts ASC, message_id ASC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        rows = await cur.fetchall()
        data = [
            {
                "message_id": r["message_id"],
                "from": r["from_msisdn"],
                "to": r["to_msisdn"],
                "ts": r["ts"],
                "text": r["text"],
            }
            for r in rows
        ]
        return data, total


async def compute_stats(db_path: str) -> dict:
    async with aiosqlite.connect(db_path) as db:
        cur_total = await db.execute("SELECT COUNT(*) FROM messages")
        total_messages = int((await cur_total.fetchone())[0])

        cur_senders = await db.execute("SELECT COUNT(DISTINCT from_msisdn) FROM messages")
        senders_count = int((await cur_senders.fetchone())[0])

        cur_top = await db.execute(
            "SELECT from_msisdn, COUNT(*) AS c FROM messages GROUP BY from_msisdn "
            "ORDER BY c DESC, from_msisdn ASC LIMIT 10"
        )
        top_rows = await cur_top.fetchall()
        messages_per_sender = [{"from": r[0], "count": int(r[1])} for r in top_rows]

        cur_minmax = await db.execute("SELECT MIN(ts), MAX(ts) FROM messages")
        minmax = await cur_minmax.fetchone()
        first_ts = minmax[0] if minmax and minmax[0] is not None else None
        last_ts = minmax[1] if minmax and minmax[1] is not None else None

        return {
            "total_messages": total_messages,
            "senders_count": senders_count,
            "messages_per_sender": messages_per_sender,
            "first_message_ts": first_ts,
            "last_message_ts": last_ts,
        }
