"""Sends a nudge at each reminder time if today's session is not finished."""
import asyncio
import json
import logging
import urllib.request

from . import config, db, session

log = logging.getLogger("ccna.reminders")


def _post(url: str, data: bytes, headers: dict) -> None:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()


def send(message: str) -> None:
    if config.NTFY_URL:
        headers = {"Title": "CCNA Daily", "Priority": "high", "Tags": "books"}
        if config.APP_URL:
            headers["Click"] = config.APP_URL
        try:
            _post(config.NTFY_URL, message.encode(), headers)
        except Exception as e:  # never crash the app over a reminder
            log.warning("ntfy failed: %s", e)
    if config.DISCORD_WEBHOOK:
        text = message + (f"\n{config.APP_URL}" if config.APP_URL else "")
        try:
            _post(config.DISCORD_WEBHOOK, json.dumps({"content": text}).encode(),
                  {"Content-Type": "application/json"})
        except Exception as e:
            log.warning("discord failed: %s", e)


def due_slot(lib, now=None) -> str | None:
    """Returns the reminder slot that should fire now, or None."""
    now = now or config.now()
    day = now.date()
    if day < config.START_DATE:
        return None
    with db.get() as conn:
        if session.is_complete(conn, day):
            return None
        sent = {r[0] for r in conn.execute("SELECT slot FROM reminders_sent WHERE day=?", (day.isoformat(),))}
        due = [t for t in config.REMINDER_TIMES if now.time() >= t and t.isoformat("minutes") not in sent]
        if not due:
            return None
        slot = max(due).isoformat("minutes")
        # Mark every passed slot so a restart late in the day sends one nudge, not several.
        for t in due:
            conn.execute("INSERT OR IGNORE INTO reminders_sent(day, slot) VALUES (?,?)",
                         (day.isoformat(), t.isoformat("minutes")))
        return slot


def message_for(lib) -> str:
    day = config.today()
    with db.get() as conn:
        blocks = session.progress(conn, lib, day)
        left = [f"{b.name} {b.done}/{b.need}" for b in blocks if not b.complete]
        streak = session.streak(conn, day)
    return f"Today's CCNA session is not done. Left: {', '.join(left)}. Streak: {streak} days."


async def loop(get_lib) -> None:
    while True:
        try:
            lib = get_lib()
            if due_slot(lib):
                await asyncio.to_thread(send, message_for(lib))
        except Exception as e:
            log.warning("reminder check failed: %s", e)
        await asyncio.sleep(60)
