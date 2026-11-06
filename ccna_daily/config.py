"""Settings, read from environment variables (see deploy/ccna-daily.env)."""
import os
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent

DB_PATH = Path(os.environ.get("CCNA_DB", ROOT / "data" / "ccna.db"))
CONTENT_DIR = Path(os.environ.get("CCNA_CONTENT", ROOT / "content"))
TZ = ZoneInfo(os.environ.get("CCNA_TZ", os.environ.get("TZ", "America/New_York")))

# First study day; days before it never count as missed.
START_DATE = date.fromisoformat(os.environ.get("CCNA_START", "2026-11-06"))

# Daily minimums for each block.
NEW_CARDS_PER_DAY = int(os.environ.get("CCNA_NEW_CARDS", "30"))
DRILL_MIN = int(os.environ.get("CCNA_DRILL_MIN", "20"))
QUESTIONS_MIN = int(os.environ.get("CCNA_QUESTIONS_MIN", "20"))
LABS_MIN = int(os.environ.get("CCNA_LABS_MIN", "1"))

# Reminders fire at these local times only if today's session is unfinished.
REMINDER_TIMES = [
    time.fromisoformat(t.strip())
    for t in os.environ.get("CCNA_REMINDERS", "12:00,19:00").split(",")
    if t.strip()
]
NTFY_URL = os.environ.get("CCNA_NTFY_URL", "")  # e.g. https://ntfy.sh/my-secret-topic
DISCORD_WEBHOOK = os.environ.get("CCNA_DISCORD_WEBHOOK", "")
APP_URL = os.environ.get("CCNA_APP_URL", "")  # link included in reminders

# Topic tags that get extra weight (dylan's weak areas).
WEAK_TAGS = {"subnetting", "routing", "ipv6", "ospf", "static-routing"}


def now() -> datetime:
    return datetime.now(TZ)


def today() -> date:
    return now().date()
