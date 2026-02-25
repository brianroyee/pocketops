# PocketOps (Text-only Jarvis v0)
CLI task manager with drill-sergeant reminders for Termux.

## Termux setup
Install Termux + Termux:API (from F-Droid).

Inside Termux:
```sh
pkg update -y
pkg install -y python git sqlite termux-api
pip install -r requirements.txt
```

## Run locally
From the repo root:
```sh
python ops.py init
python ops.py add "Ship PocketOps" --due "in 45m" --priority high
python ops.py list
python ops.py check --dry-run
```

## Host once, auto-update clients
If you want one hosted source of truth and Termux clients that update automatically (instead of re-cloning):

1. Host your PocketOps repo in GitHub/GitLab (or publish wheels).
2. On each Termux device, set the update source once:
```sh
python ops.py update-config --source "git+https://github.com/<your-org>/pocketops.git"
```
3. Update manually anytime:
```sh
python ops.py self-update
```
4. Schedule auto-updates + reminder checks using `crond`/Termux job scheduler:
```sh
# every 15 minutes reminder check
*/15 * * * * cd ~/pocketops && python ops.py check --quiet

# every 6 hours self-update
0 */6 * * * cd ~/pocketops && python ops.py self-update
```

Notes:
- `self-update` uses `python -m pip install --upgrade <source>` under the hood.
- Keep your task DB local on each device (`~/.pocketops/pocketops.db`).

## Commands
```text
init         Initialize database
add          Add a task
list         List tasks
done         Mark task as done
snooze       Snooze task (strict)
check        Run reminder engine once
stats        Show accountability stats
update-config Configure self-update source
self-update  Pull latest release from configured source
```
