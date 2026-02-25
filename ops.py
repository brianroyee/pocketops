#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    repo_parent = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))
    if repo_parent not in sys.path:
        sys.path.insert(0, repo_parent)

from pocketops.db import DB
from pocketops.timeparse import parse_due
from pocketops.engine import run_check, format_task_list

DEFAULT_DB_PATH = os.path.expanduser("~/.pocketops/pocketops.db")
DEFAULT_UPDATE_SOURCE = "git+https://github.com/<your-org>/pocketops.git"
CONFIG_DIR = Path.home() / ".pocketops"
CONFIG_PATH = CONFIG_DIR / "client.json"


def ensure_parent_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)


def load_client_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception:
        return {}


def save_client_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, sort_keys=True) + "\n")


def cmd_init(args) -> int:
    db_path = args.db
    ensure_parent_dir(db_path)
    db = DB(db_path)
    db.init()
    print(f"✅ Initialized DB at: {db_path}")
    return 0


def cmd_add(args) -> int:
    db = DB(args.db)
    db.init()

    due_at = None
    if args.due:
        due_at = parse_due(args.due)
        if due_at is None:
            print("❌ Could not parse --due. Use e.g. '2026-02-26 23:30' or 'in 30m' or '10pm'.")
            return 2

    task_id = db.add_task(
        title=args.title.strip(),
        due_at=due_at,
        priority=args.priority,
    )
    due_str = due_at.strftime("%Y-%m-%d %H:%M") if due_at else "—"
    print(f"✅ Added task #{task_id}: {args.title}")
    print(f"   Due: {due_str} | Priority: {args.priority}")
    return 0


def cmd_list(args) -> int:
    db = DB(args.db)
    db.init()
    tasks = db.list_tasks(status=args.status)
    print(format_task_list(tasks))
    return 0


def cmd_done(args) -> int:
    db = DB(args.db)
    db.init()
    ok = db.mark_done(args.id)
    if not ok:
        print(f"❌ No open task found with id {args.id}")
        return 2
    print(f"✅ Marked done: #{args.id}")
    return 0


def cmd_snooze(args) -> int:
    db = DB(args.db)
    db.init()
    until = parse_due(f"in {args.duration}")
    if until is None:
        print("❌ Bad snooze duration. Examples: 15m, 30m, 2h, 1d")
        return 2
    ok = db.snooze_task(args.id, until)
    if not ok:
        print(f"❌ No open task found with id {args.id}")
        return 2
    print(f"⏳ Snoozed #{args.id} until {until.strftime('%Y-%m-%d %H:%M')}")
    return 0


def cmd_check(args) -> int:
    db = DB(args.db)
    db.init()
    summary = run_check(db, dry_run=args.dry_run)
    if args.quiet:
        return 0
    print(summary)
    return 0


def cmd_stats(args) -> int:
    db = DB(args.db)
    db.init()
    stats = db.get_stats()
    print(f"📌 Open tasks: {stats['open_tasks']}")
    print(f"✅ Done today: {stats['done_today']}")
    print(f"🔥 Completion streak (days with ≥1 completion): {stats['streak_days']}")
    print(f"⚠️ Overdue open tasks: {stats['overdue_open']}")
    print(f"😤 Reminders sent today: {stats['reminders_today']}")
    return 0


def cmd_update_config(args) -> int:
    cfg = load_client_config()
    if args.source:
        cfg["update_source"] = args.source
    if args.interval_hours is not None:
        cfg["update_interval_hours"] = args.interval_hours
    save_client_config(cfg)
    print(f"✅ Saved client config to {CONFIG_PATH}")
    print(json.dumps(cfg, indent=2, sort_keys=True))
    return 0


def cmd_self_update(args) -> int:
    cfg = load_client_config()
    source = args.source or cfg.get("update_source") or DEFAULT_UPDATE_SOURCE

    if "<your-org>" in source:
        print("❌ Set a real update source first: ops update-config --source 'git+https://...'")
        return 2

    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", source]
    print(f"🔄 Updating from: {source}")
    print("$ " + " ".join(cmd))

    if args.dry_run:
        print("✅ Dry run only; no package update executed.")
        return 0

    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print("❌ Update failed.")
        return result.returncode

    print("✅ Update completed.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ops", description="PocketOps: CLI task manager with accountability reminders.")
    p.add_argument("--db", default=DEFAULT_DB_PATH, help=f"Path to SQLite DB (default: {DEFAULT_DB_PATH})")

    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="Initialize database")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("add", help="Add a task")
    sp.add_argument("title", help="Task title (wrap in quotes)")
    sp.add_argument("--due", help="Due time (e.g., '2026-02-26 23:30', '10pm', 'in 30m')", default=None)
    sp.add_argument("--priority", choices=["low", "med", "high"], default="med")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("list", help="List tasks")
    sp.add_argument("--status", choices=["open", "done", "all"], default="open")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("done", help="Mark task as done")
    sp.add_argument("id", type=int, help="Task id")
    sp.set_defaults(func=cmd_done)

    sp = sub.add_parser("snooze", help="Snooze task (strict)")
    sp.add_argument("id", type=int, help="Task id")
    sp.add_argument("duration", help="Duration (e.g., 15m, 30m, 2h, 1d)")
    sp.set_defaults(func=cmd_snooze)

    sp = sub.add_parser("check", help="Run reminder engine once")
    sp.add_argument("--dry-run", action="store_true", help="Don't send notifications, just print what would happen")
    sp.add_argument("--quiet", action="store_true", help="Print nothing (useful for schedulers)")
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("stats", help="Show accountability stats")
    sp.set_defaults(func=cmd_stats)

    sp = sub.add_parser("update-config", help="Configure where self-update pulls releases from")
    sp.add_argument("--source", help="pip-installable source, e.g. git+https://... or wheel URL")
    sp.add_argument("--interval-hours", type=int, help="Optional metadata for your scheduler cadence")
    sp.set_defaults(func=cmd_update_config)

    sp = sub.add_parser("self-update", help="Update PocketOps from configured remote source")
    sp.add_argument("--source", help="Override configured update source")
    sp.add_argument("--dry-run", action="store_true", help="Print update command without executing")
    sp.set_defaults(func=cmd_self_update)

    return p


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
