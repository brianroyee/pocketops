import shutil
import subprocess

def can_notify() -> bool:
    return shutil.which("termux-notification") is not None

def send(title: str, content: str, ongoing: bool = False) -> None:
    if not can_notify():
        # fallback to console
        print(f"[NOTIFY] {title} — {content}")
        return

    cmd = [
        "termux-notification",
        "--title", title,
        "--content", content,
    ]
    if ongoing:
        cmd.append("--ongoing")

    # Don't crash if Termux API permissions not granted yet
    try:
        subprocess.run(cmd, check=False)
    except Exception:
        print(f"[NOTIFY FAIL] {title} — {content}")