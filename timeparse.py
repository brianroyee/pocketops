from datetime import datetime, timedelta
import re
from dateutil import parser as dtparser

def parse_due(text: str):
    """
    Supports:
      - ISO-ish: "2026-02-26 23:30"
      - Natural: "10pm", "tomorrow 9am" (best-effort via dateutil)
      - Relative: "in 30m", "in 2h", "in 1d"
    Returns datetime or None.
    """
    if not text:
        return None
    t = text.strip().lower()

    m = re.fullmatch(r"in\s+(\d+)\s*([mhd])", t)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        now = datetime.now()
        if unit == "m":
            return now + timedelta(minutes=n)
        if unit == "h":
            return now + timedelta(hours=n)
        if unit == "d":
            return now + timedelta(days=n)

    # try dateutil parse (uses current datetime as default)
    try:
        now = datetime.now()
        # If user says "10pm", dateutil uses today's date by default -> good.
        dt = dtparser.parse(text, default=now, fuzzy=True)
        return dt.replace(second=0, microsecond=0)
    except Exception:
        return None