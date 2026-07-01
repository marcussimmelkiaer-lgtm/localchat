from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

# SQLite persistence for conversations + messages. WAL mode so the sidebar can
# read while a generation worker writes. One short-lived connection per op keeps
# things thread-safe across the uvicorn loop and generation worker threads.

_db_path: str | None = None
_init_lock = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db(path: str) -> None:
    global _db_path
    with _init_lock:
        _db_path = path
        with _conn() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'done',
                    stats TEXT,
                    error TEXT,
                    attachments TEXT NOT NULL DEFAULT '[]',
                    ord INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                )
                """
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, ord)"
            )
            # Migrate older DBs that predate the attachments column.
            cols = {r["name"] for r in c.execute("PRAGMA table_info(messages)").fetchall()}
            if "attachments" not in cols:
                c.execute("ALTER TABLE messages ADD COLUMN attachments TEXT NOT NULL DEFAULT '[]'")


@contextmanager
def _conn():
    assert _db_path is not None, "store not initialised"
    conn = sqlite3.connect(_db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _row_to_conv(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"],
        "title": r["title"] or "",
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }


def _row_to_msg(r: sqlite3.Row) -> dict:
    stats = None
    if r["stats"]:
        try:
            stats = json.loads(r["stats"])
        except Exception:  # noqa: BLE001
            stats = None
    attachments: list[dict] = []
    raw_att = r["attachments"] if "attachments" in r.keys() else None
    if raw_att:
        try:
            attachments = json.loads(raw_att) or []
        except Exception:  # noqa: BLE001
            attachments = []
    return {
        "id": r["id"],
        "role": r["role"],
        "content": r["content"] or "",
        "status": r["status"] or "done",
        "stats": stats,
        "error": r["error"],
        # Full metadata incl. extracted `text` (used by prompt_from_store);
        # MessageOut strips `text`/`data` before it reaches the UI.
        "attachments": attachments,
        "created_at": r["created_at"],
    }


# --- conversations ---

def list_conversations() -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM conversations ORDER BY updated_at DESC"
        ).fetchall()
        return [_row_to_conv(r) for r in rows]


def create_conversation(conv_id: str, title: str = "") -> dict:
    ts = now_iso()
    with _conn() as c:
        c.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?,?,?,?)",
            (conv_id, title, ts, ts),
        )
    return {"id": conv_id, "title": title, "created_at": ts, "updated_at": ts}


def get_conversation(conv_id: str) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM conversations WHERE id=?", (conv_id,)).fetchone()
        return _row_to_conv(r) if r else None


def get_messages(conv_id: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY ord ASC", (conv_id,)
        ).fetchall()
        return [_row_to_msg(r) for r in rows]


def get_message(msg_id: str) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM messages WHERE id=?", (msg_id,)).fetchone()
        return _row_to_msg(r) if r else None


def rename_conversation(conv_id: str, title: str) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE conversations SET title=?, updated_at=? WHERE id=?",
            (title, now_iso(), conv_id),
        )


def touch_conversation(conv_id: str) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE conversations SET updated_at=? WHERE id=?", (now_iso(), conv_id)
        )


def delete_conversation(conv_id: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM messages WHERE conversation_id=?", (conv_id,))
        c.execute("DELETE FROM conversations WHERE id=?", (conv_id,))


# --- messages ---

def _next_ord(c: sqlite3.Connection, conv_id: str) -> int:
    r = c.execute(
        "SELECT COALESCE(MAX(ord), -1) + 1 AS n FROM messages WHERE conversation_id=?",
        (conv_id,),
    ).fetchone()
    return int(r["n"])


def add_message(
    msg_id: str,
    conv_id: str,
    role: str,
    content: str = "",
    status: str = "done",
    stats: dict | None = None,
    error: str | None = None,
    attachments: list[dict] | None = None,
) -> dict:
    ts = now_iso()
    att_json = json.dumps(attachments or [])
    with _conn() as c:
        ordn = _next_ord(c, conv_id)
        c.execute(
            "INSERT INTO messages (id, conversation_id, role, content, status, stats, error, attachments, ord, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (msg_id, conv_id, role, content, status, json.dumps(stats) if stats else None, error, att_json, ordn, ts),
        )
        c.execute("UPDATE conversations SET updated_at=? WHERE id=?", (ts, conv_id))
    return {
        "id": msg_id,
        "role": role,
        "content": content,
        "status": status,
        "stats": stats,
        "error": error,
        "attachments": attachments or [],
        "created_at": ts,
    }


def update_message(
    msg_id: str,
    content: str | None = None,
    status: str | None = None,
    stats: dict | None = None,
    error: str | None = None,
) -> None:
    sets, params = [], []
    if content is not None:
        sets.append("content=?")
        params.append(content)
    if status is not None:
        sets.append("status=?")
        params.append(status)
    if stats is not None:
        sets.append("stats=?")
        params.append(json.dumps(stats))
    if error is not None:
        sets.append("error=?")
        params.append(error)
    if not sets:
        return
    params.append(msg_id)
    with _conn() as c:
        c.execute(f"UPDATE messages SET {', '.join(sets)} WHERE id=?", params)


def delete_message(msg_id: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM messages WHERE id=?", (msg_id,))


def delete_last_assistant(conv_id: str) -> str | None:
    """Delete the trailing assistant message (for regenerate). Returns its id."""
    with _conn() as c:
        r = c.execute(
            "SELECT id, role FROM messages WHERE conversation_id=? ORDER BY ord DESC LIMIT 1",
            (conv_id,),
        ).fetchone()
        if r and r["role"] == "assistant":
            c.execute("DELETE FROM messages WHERE id=?", (r["id"],))
            return r["id"]
        return None
