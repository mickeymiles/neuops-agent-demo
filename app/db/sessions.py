# -*- coding: utf-8 -*-
"""会话域：对话 / 项目 / 分享 / 历史加载"""

from datetime import datetime
import json
import uuid

from seed_data import MOCK_CONV_MESSAGES

from .base import (
    _db_lock,
    _get_conn,
)

def ensure_conversation(conv_id: str, title: str) -> None:
    """新建会话；若已存在则更新标题"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at",
                (conv_id, title, now, now),
            )
            conn.commit()
        finally:
            conn.close()


def save_user_message(conv_id: str, content: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, 'user', ?, ?)",
                (conv_id, content, now),
            )
            conn.commit()
        finally:
            conn.close()


def save_agent_message(conv_id: str, thought: str, tools: list, conclusion: str, route: dict,
                       engine: str = None, dsh_session_id: str = None) -> None:
    """保存 agent 消息；engine / dsh_session_id 用于更新会话的引擎观测字段（P3）"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, thought, tools, conclusion, route, created_at) "
                "VALUES (?, 'agent', ?, ?, ?, ?, ?)",
                (conv_id, thought, json.dumps(tools, ensure_ascii=False), conclusion,
                 json.dumps(route, ensure_ascii=False) if route else "", now),
            )
            if engine is not None or dsh_session_id is not None:
                sets = ["updated_at=?"]
                vals = [now]
                if engine is not None:
                    sets.append("engine=?")
                    vals.append(engine)
                if dsh_session_id is not None:
                    sets.append("dsh_session_id=?")
                    vals.append(dsh_session_id)
                vals.append(conv_id)
                conn.execute(f"UPDATE conversations SET {', '.join(sets)} WHERE id=?", vals)
            conn.commit()
        finally:
            conn.close()


def list_conversations() -> list:
    with _db_lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT id, title, created_at, updated_at, project_id, pinned, share_id "
                "FROM conversations ORDER BY pinned DESC, updated_at DESC"
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["pinned"] = bool(d.get("pinned", 0))
                result.append(d)
            return result
        finally:
            conn.close()


# ═══════════════════════════════════════════
# 项目 CRUD
# ═══════════════════════════════════════════


def db_create_project(name: str) -> str:
    """新建项目，返回项目 ID"""
    pid = "proj-" + uuid.uuid4().hex[:8]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO projects (id, name, created_at) VALUES (?, ?, ?)",
                (pid, name, now),
            )
            conn.commit()
        finally:
            conn.close()
    return pid


def db_list_projects() -> list:
    with _db_lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT p.id, p.name, p.created_at, "
                "(SELECT COUNT(*) FROM conversations c WHERE c.project_id = p.id) AS conv_count "
                "FROM projects p ORDER BY p.created_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def db_rename_project(project_id: str, name: str) -> bool:
    with _db_lock:
        conn = _get_conn()
        try:
            cur = conn.execute("UPDATE projects SET name=? WHERE id=?", (name, project_id))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def db_delete_project(project_id: str) -> None:
    """删除项目，同时把其下会话移回「未分组」"""
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("UPDATE conversations SET project_id='' WHERE project_id=?", (project_id,))
            conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
            conn.commit()
        finally:
            conn.close()


# ═══════════════════════════════════════════
# 会话操作：置顶 / 重命名 / 移动 / 删除 / 分享
# ═══════════════════════════════════════════


def db_update_conversation(conv_id: str, fields: dict) -> bool:
    """按需更新会话字段（title / project_id / pinned），返回是否命中记录"""
    allowed = {"title", "project_id", "pinned"}
    sets, params = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k}=?")
            params.append(v)
    if not sets:
        return False
    params.append(conv_id)
    with _db_lock:
        conn = _get_conn()
        try:
            cur = conn.execute(
                f"UPDATE conversations SET {', '.join(sets)} WHERE id=?",
                params,
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def db_delete_conversation(conv_id: str) -> None:
    """删除会话及其全部消息"""
    with _db_lock:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM messages WHERE conversation_id=?", (conv_id,))
            conn.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
            conn.commit()
        finally:
            conn.close()


def db_get_deleted_mock_convs() -> list:
    """读取已删除的 mock 会话 id 列表（meta 标记，保证刷新后不再出现）"""
    with _db_lock:
        conn = _get_conn()
        try:
            row = conn.execute("SELECT value FROM meta WHERE key='deleted_mock_convs'").fetchone()
            if row and row["value"]:
                try:
                    return json.loads(row["value"])
                except Exception:
                    return []
            return []
        finally:
            conn.close()


def db_mark_mock_conv_deleted(conv_id: str) -> None:
    """记录会话删除标记（幂等）。

    真实会话删除时已删库记录；数字员工详情里的预置 mock 会话不在库中，
    靠该标记持久化「已删除」状态，避免刷新后重新出现。
    """
    if not conv_id:
        return
    with _db_lock:
        conn = _get_conn()
        try:
            cur = []
            row = conn.execute("SELECT value FROM meta WHERE key='deleted_mock_convs'").fetchone()
            if row and row["value"]:
                try:
                    cur = json.loads(row["value"])
                except Exception:
                    cur = []
            if conv_id not in cur:
                cur.append(conv_id)
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('deleted_mock_convs', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (json.dumps(cur, ensure_ascii=False),),
                )
                conn.commit()
        finally:
            conn.close()


def db_share_conversation(conv_id: str) -> str:
    """为会话生成/复用分享 ID（短随机串），返回 share_id"""
    share_id = "s" + uuid.uuid4().hex[:8]
    with _db_lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT share_id FROM conversations WHERE id=?", (conv_id,)
            ).fetchone()
            if row and row["share_id"]:
                return row["share_id"]
            conn.execute("UPDATE conversations SET share_id=? WHERE id=?", (share_id, conv_id))
            conn.commit()
        finally:
            conn.close()
    return share_id


def db_get_employee_conversations(emp_id: str) -> list:
    """获取指定员工的关联对话列表。

    由于 conversations 表无 employee_id 列，此处返回最近的 N 条会话
    （按 updated_at 倒序），供员工详情页展示。格式兼容前端预期：
    {id, title, start_time, message_count}
    """
    with _db_lock:
        conn = _get_conn()
        try:
            rows = conn.execute(
                """SELECT c.id, c.title, c.updated_at AS start_time,
                          (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count
                   FROM conversations c
                   ORDER BY c.updated_at DESC
                   LIMIT 20"""
            ).fetchall()
            return [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "start_time": r["start_time"] or "",
                    "message_count": r["message_count"],
                }
                for r in rows
            ]
        finally:
            conn.close()


def db_get_conversation_share(conv_id: str) -> str:
    with _db_lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT share_id FROM conversations WHERE id=?", (conv_id,)
            ).fetchone()
            return (row["share_id"] if row else "") or ""
        finally:
            conn.close()


def db_get_conv_by_share(share_id: str):
    """通过 share_id 定位会话，返回 (conv_id, title) 或 None"""
    with _db_lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT id, title FROM conversations WHERE share_id=?", (share_id,)
            ).fetchone()
            return (row["id"], row["title"]) if row else None
        finally:
            conn.close()


def get_conversation_messages(conv_id: str) -> dict:
    with _db_lock:
        conn = _get_conn()
        try:
            conv = conn.execute("SELECT id, title FROM conversations WHERE id=?", (conv_id,)).fetchone()
            if not conv:
                return {"conversation_id": conv_id, "title": "新会话", "messages": []}
            rows = conn.execute(
                "SELECT role, content, thought, tools, conclusion, route FROM messages WHERE conversation_id=? ORDER BY id ASC",
                (conv_id,),
            ).fetchall()
            messages = []
            for r in rows:
                if r["role"] == "user":
                    messages.append({"role": "user", "content": r["content"]})
                else:
                    messages.append({
                        "role": "agent",
                        "thought": r["thought"],
                        "tools": json.loads(r["tools"] or "[]"),
                        "conclusion": r["conclusion"],
                        "route": json.loads(r["route"]) if r["route"] else None,
                    })
            return {"conversation_id": conv_id, "title": conv["title"], "messages": messages}
        finally:
            conn.close()


def _load_chat_history(conv_id: str, max_turns: int = 6) -> list:
    """读取会话历史，转为可喂给模型的 messages（只取 user 内容 + agent 结论），取最近 N 轮"""
    if not conv_id:
        return []
    data = get_conversation_messages(conv_id)
    history = []
    for m in data.get("messages", []):
        if m["role"] == "user":
            history.append({"role": "user", "content": m["content"]})
        else:
            conclusion = m.get("conclusion", "")
            if conclusion:
                history.append({"role": "assistant", "content": conclusion[:800]})
    # 每轮 = 1 user + 1 assistant，取最近 max_turns 轮
    return history[-(max_turns * 2):]


def seed_mock_conversations():
    """首次初始化时导入预置会话（meta 标记，仅导入一次）"""
    with _db_lock:
        conn = _get_conn()
        try:
            if conn.execute("SELECT value FROM meta WHERE key='conv_seeded'").fetchone():
                return
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for cid, cdata in MOCK_CONV_MESSAGES.items():
                conn.execute(
                    "INSERT OR REPLACE INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (cid, cdata.get("title", cid), now, now),
                )
                for m in cdata.get("messages", []):
                    if m["role"] == "user":
                        conn.execute(
                            "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, 'user', ?, ?)",
                            (cid, m.get("content", ""), now),
                        )
                    else:
                        conn.execute(
                            "INSERT INTO messages (conversation_id, role, thought, tools, conclusion, route, created_at) "
                            "VALUES (?, 'agent', ?, ?, ?, '', ?)",
                            (cid, m.get("thought", ""), json.dumps(m.get("tools", []), ensure_ascii=False),
                             m.get("conclusion", ""), now),
                        )
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('conv_seeded', '1')")
            conn.commit()
        finally:
            conn.close()
