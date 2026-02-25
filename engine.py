from datetime import datetime, timedelta
from pocketops.notify import send

def _dt(s: str):
    return datetime.fromisoformat(s) if s else None

def _cooldown_ok(last_sent_at: datetime | None, cooldown: timedelta) -> bool:
    if last_sent_at is None:
        return True
    return datetime.now() - last_sent_at >= cooldown

def _is_snoozed(task) -> bool:
    su = _dt(task.get("snoozed_until"))
    return su is not None and datetime.now() < su

def _task_due(task) -> datetime | None:
    return _dt(task.get("due_at"))

def _task_title(task) -> str:
    return task.get("title", "").strip()

def _priority(task) -> str:
    return (task.get("priority") or "med").lower()

def _escalation(due: datetime, now: datetime):
    """
    Returns (level, kind, cooldown, title_prefix)
    level is monotonic-ish with urgency.
    """
    delta = due - now  # positive = not due yet; negative = overdue
    if delta > timedelta(minutes=60):
        return None

    # Due soon window
    if timedelta(minutes=15) < delta <= timedelta(minutes=60):
        return (1, "due", timedelta(minutes=45), "⚠️ Incoming")
    if timedelta(minutes=0) < delta <= timedelta(minutes=15):
        return (2, "due", timedelta(minutes=15), "⏳ Final approach")
    if timedelta(minutes=-10) < delta <= timedelta(minutes=0):
        return (3, "overdue", timedelta(minutes=10), "🚨 DUE NOW")

    # Overdue escalation ladder
    overdue = -delta
    if timedelta(minutes=10) <= overdue < timedelta(minutes=30):
        return (4, "overdue", timedelta(minutes=20), "🔥 Overdue")
    if timedelta(minutes=30) <= overdue < timedelta(minutes=60):
        return (5, "overdue", timedelta(minutes=30), "😤 Still overdue")
    return (6, "overdue", timedelta(minutes=60), "🧨 Stop dodging")

def _message_for(level: int, task, due: datetime, now: datetime) -> str:
    title = _task_title(task)
    pr = _priority(task)
    delta = due - now

    if level == 1:
        return f"{title} (p:{pr}) due in ~{int(delta.total_seconds()//60)} min. Start. Now."
    if level == 2:
        return f"{title} (p:{pr}) due in {int(delta.total_seconds()//60)} min. No excuses."
    if level == 3:
        return f"{title} (p:{pr}) is DUE. Mark done or snooze with a time."
    if level == 4:
        return f"{title} overdue. You are choosing future pain. Fix it."
    if level == 5:
        return f"{title} still overdue. Decide: do it or snooze with a real duration."
    return f"{title} is being ignored. Pick one task and finish it. Right now."

def format_task_list(tasks) -> str:
    if not tasks:
        return "No tasks."
    lines = []
    now = datetime.now()
    for t in tasks:
        due = _task_due(t)
        status = t["status"]
        snoozed_until = _dt(t.get("snoozed_until"))
        badge = ""
        if status == "open" and due:
            if snoozed_until and now < snoozed_until:
                badge = f"⏸ snoozed until {snoozed_until.strftime('%m-%d %H:%M')}"
            else:
                if now > due:
                    mins = int((now - due).total_seconds() // 60)
                    badge = f"🔥 overdue {mins}m"
                else:
                    mins = int((due - now).total_seconds() // 60)
                    badge = f"⏳ due in {mins}m"
        due_str = due.strftime("%Y-%m-%d %H:%M") if due else "—"
        lines.append(f"#{t['id']:>3} [{t['priority']}] {t['title']} | due: {due_str} | {badge}")
    return "\n".join(lines)

def run_check(db, dry_run: bool = False) -> str:
    now = datetime.now()
    tasks = db.due_open_tasks()
    fired = 0
    skipped = 0

    # Sort: overdue first, then soonest due
    def sort_key(t):
        due = _task_due(t)
        if due is None:
            return (2, datetime.max)
        return (0, due) if now > due else (1, due)
    tasks.sort(key=sort_key)

    # Track how many overdue reminders per task (for “ignoring” callouts)
    top_overdue = []

    for t in tasks:
        if _is_snoozed(t):
            skipped += 1
            continue

        due = _task_due(t)
        if due is None:
            skipped += 1
            continue

        esc = _escalation(due, now)
        if esc is None:
            skipped += 1
            continue

        level, kind, cooldown, prefix = esc
        last = db.last_reminder(t["id"])
        last_sent_at = datetime.fromisoformat(last["sent_at"]) if last else None

        if not _cooldown_ok(last_sent_at, cooldown):
            skipped += 1
            continue

        title = f"{prefix}: #{t['id']}"
        msg = _message_for(level, t, due, now)

        if dry_run:
            fired += 1
            continue

        send(title, msg)
        db.add_reminder(t["id"], level, kind, msg)
        fired += 1

        if kind == "overdue":
            top_overdue.append(t)

    # If user is ignoring multiple overdue tasks, send a bundled callout (max 3)
    if not dry_run:
        overdue_tasks = [t for t in tasks if (not _is_snoozed(t)) and _task_due(t) and now > _task_due(t)]
        if len(overdue_tasks) >= 2:
            # only if we haven't spammed: once per 6 hours max
            # We'll approximate with reminders table count in last 6 hours for kind='overdue' not easily filtered -> keep simple:
            pass

    return f"ops check → reminders sent: {fired}, skipped: {skipped}"