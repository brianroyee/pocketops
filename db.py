import sqlite3
import os
from datetime import datetime, timedelta

def now_local() -> datetime:
    return datetime.now()

class DB:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with self._conn() as c:
            c.executescript("""
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS tasks (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              title TEXT NOT NULL,
              priority TEXT NOT NULL DEFAULT 'med',
              status TEXT NOT NULL DEFAULT 'open',
              created_at TEXT NOT NULL,
              due_at TEXT NULL,
              snoozed_until TEXT NULL,
              completed_at TEXT NULL
            );

            CREATE TABLE IF NOT EXISTS reminders (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              task_id INTEGER NOT NULL,
              sent_at TEXT NOT NULL,
              level INTEGER NOT NULL,
              kind TEXT NOT NULL, -- 'due' or 'overdue'
              message TEXT NOT NULL,
              FOREIGN KEY(task_id) REFERENCES tasks(id)
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(due_at);
            CREATE INDEX IF NOT EXISTS idx_reminders_task ON reminders(task_id, sent_at);
            """)

    def add_task(self, title: str, due_at, priority: str) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO tasks(title, priority, status, created_at, due_at) VALUES(?,?,?,?,?)",
                (title, priority, "open", now_local().isoformat(timespec="seconds"),
                 due_at.isoformat(timespec="seconds") if due_at else None),
            )
            return int(cur.lastrowid)

    def list_tasks(self, status: str = "open"):
        with self._conn() as c:
            if status == "all":
                rows = c.execute("SELECT * FROM tasks ORDER BY status, due_at IS NULL, due_at").fetchall()
            else:
                rows = c.execute("SELECT * FROM tasks WHERE status=? ORDER BY due_at IS NULL, due_at", (status,)).fetchall()
            return [dict(r) for r in rows]

    def get_task(self, task_id: int):
        with self._conn() as c:
            r = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            return dict(r) if r else None

    def mark_done(self, task_id: int) -> bool:
        with self._conn() as c:
            cur = c.execute(
                "UPDATE tasks SET status='done', completed_at=? WHERE id=? AND status='open'",
                (now_local().isoformat(timespec="seconds"), task_id),
            )
            return cur.rowcount > 0

    def snooze_task(self, task_id: int, until: datetime) -> bool:
        with self._conn() as c:
            cur = c.execute(
                "UPDATE tasks SET snoozed_until=? WHERE id=? AND status='open'",
                (until.isoformat(timespec="seconds"), task_id),
            )
            return cur.rowcount > 0

    def due_open_tasks(self):
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM tasks WHERE status='open' AND due_at IS NOT NULL"
            ).fetchall()
            return [dict(r) for r in rows]

    def add_reminder(self, task_id: int, level: int, kind: str, message: str):
        with self._conn() as c:
            c.execute(
                "INSERT INTO reminders(task_id, sent_at, level, kind, message) VALUES(?,?,?,?,?)",
                (task_id, now_local().isoformat(timespec="seconds"), level, kind, message),
            )

    def last_reminder(self, task_id: int):
        with self._conn() as c:
            r = c.execute(
                "SELECT * FROM reminders WHERE task_id=? ORDER BY sent_at DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            return dict(r) if r else None

    def reminders_since(self, since: datetime) -> int:
        with self._conn() as c:
            r = c.execute(
                "SELECT COUNT(*) as n FROM reminders WHERE sent_at >= ?",
                (since.isoformat(timespec="seconds"),),
            ).fetchone()
            return int(r["n"])

    def get_stats(self):
        now = now_local()
        start_today = datetime(now.year, now.month, now.day)
        with self._conn() as c:
            open_tasks = c.execute("SELECT COUNT(*) n FROM tasks WHERE status='open'").fetchone()["n"]
            done_today = c.execute(
                "SELECT COUNT(*) n FROM tasks WHERE status='done' AND completed_at >= ?",
                (start_today.isoformat(timespec="seconds"),)
            ).fetchone()["n"]

            overdue_open = c.execute(
                "SELECT COUNT(*) n FROM tasks WHERE status='open' AND due_at IS NOT NULL AND due_at < ?",
                (now.isoformat(timespec="seconds"),)
            ).fetchone()["n"]

            reminders_today = c.execute(
                "SELECT COUNT(*) n FROM reminders WHERE sent_at >= ?",
                (start_today.isoformat(timespec="seconds"),)
            ).fetchone()["n"]

        # simple streak: count backwards days until a day with 0 completions
        streak = 0
        day = start_today
        while True:
            next_day = day + timedelta(days=1)
            with self._conn() as c:
                n = c.execute(
                    "SELECT COUNT(*) n FROM tasks WHERE completed_at >= ? AND completed_at < ?",
                    (day.isoformat(timespec="seconds"), next_day.isoformat(timespec="seconds")),
                ).fetchone()["n"]
            if n > 0:
                streak += 1
                day = day - timedelta(days=1)
            else:
                break

        return {
            "open_tasks": int(open_tasks),
            "done_today": int(done_today),
            "streak_days": int(streak),
            "overdue_open": int(overdue_open),
            "reminders_today": int(reminders_today),
        }