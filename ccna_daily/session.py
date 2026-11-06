"""Daily session logic: what is due, what counts, when the day is complete."""
import random
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

from . import config, srs
from .content import Library

BLOCKS = ["cards", "drill", "questions", "lab"]
BLOCK_NAMES = {
    "cards": "Flash cards",
    "drill": "Subnetting drill",
    "questions": "Practice questions",
    "lab": "Troubleshooting lab",
}


@dataclass
class BlockProgress:
    key: str
    name: str
    done: int
    need: int
    complete: bool

    @property
    def pct(self) -> int:
        if self.need <= 0:
            return 100
        return min(100, round(100 * self.done / self.need))


def _d(day: date) -> str:
    return day.isoformat()


def is_complete(conn: sqlite3.Connection, day: date) -> bool:
    return conn.execute("SELECT 1 FROM completions WHERE day=?", (_d(day),)).fetchone() is not None


def missed_yesterday(conn: sqlite3.Connection, day: date) -> bool:
    y = day - timedelta(days=1)
    return y >= config.START_DATE and not is_complete(conn, y)


def minimums(conn: sqlite3.Connection, day: date) -> dict[str, int]:
    """Daily minimums. A missed day rolls half its drill and question work into today."""
    factor = 1.5 if missed_yesterday(conn, day) else 1.0
    return {
        "drill": round(config.DRILL_MIN * factor),
        "questions": round(config.QUESTIONS_MIN * factor),
        "lab": config.LABS_MIN,
    }


# ---------- cards ----------

def _available_topics(lib: Library, day: date) -> set[str] | None:
    """Topics whose scheduled day has arrived. None means no schedule, so all topics."""
    first = lib.topic_first_day()
    if not first:
        return None
    all_topics = {c.topic for c in lib.cards.values()} | {q.topic for q in lib.questions.values()}
    # Topics not in the schedule at all are always available.
    return {t for t in all_topics if t not in first or first[t] <= day}


def _introduced_today(conn, day: date) -> int:
    return conn.execute("SELECT COUNT(*) FROM card_state WHERE introduced_on=?", (_d(day),)).fetchone()[0]


def _new_candidates(conn, lib: Library, day: date, topic: str | None) -> list[str]:
    known = {r[0] for r in conn.execute("SELECT card_id FROM card_state")}
    first = lib.topic_first_day()
    avail = _available_topics(lib, day)
    cards = [c for c in lib.cards.values() if c.id not in known]
    if topic:
        return [c.id for c in cards if c.topic == topic]
    pool = [c for c in cards if avail is None or c.topic in avail]
    if not pool:
        pool = cards  # everything scheduled is learned: pull from upcoming topics
    far = date.max
    # Earliest-scheduled topics first, weak topics first within a day, file order after that.
    pool.sort(key=lambda c: (first.get(c.topic, far) if first.get(c.topic, far) <= day else far,
                             0 if c.topic in config.WEAK_TAGS else 1))
    return [c.id for c in pool]


def _due_ids(conn, lib: Library, day: date) -> list[str]:
    rows = conn.execute(
        "SELECT card_id FROM card_state WHERE due<=? ORDER BY last_review IS NOT NULL, last_review",
        (_d(day),),
    ).fetchall()
    return [r[0] for r in rows if r[0] in lib.cards]


def cards_remaining(conn, lib: Library, day: date) -> int:
    allowance = max(0, config.NEW_CARDS_PER_DAY - _introduced_today(conn, day))
    return len(_due_ids(conn, lib, day)) + min(allowance, len(_new_candidates(conn, lib, day, None)))


def next_card(conn, lib: Library, day: date, extra_topic: str | None = None, extra: bool = False) -> str | None:
    """Next card to show. Introduces a new card when nothing is due and the daily allowance remains.

    extra=True ignores the new-card allowance (study-ahead mode).
    """
    due = _due_ids(conn, lib, day)
    if extra_topic:
        due = [cid for cid in due if lib.cards[cid].topic == extra_topic]
    if due:
        return due[0]
    if not extra and _introduced_today(conn, day) >= config.NEW_CARDS_PER_DAY:
        return None
    cands = _new_candidates(conn, lib, day, extra_topic)
    if not cands:
        return None
    cid = cands[0]
    conn.execute(
        "INSERT INTO card_state(card_id, introduced_on, due) VALUES (?,?,?)",
        (cid, _d(day), _d(day)),
    )
    return cid


def rate_card(conn, card_id: str, rating: int, day: date) -> None:
    row = conn.execute("SELECT * FROM card_state WHERE card_id=?", (card_id,)).fetchone()
    if row is None:
        return
    state = srs.State(row["interval_days"], row["ease"], row["reps"], row["lapses"])
    new, due = srs.review(state, rating, day)
    now = config.now().isoformat()
    conn.execute(
        "UPDATE card_state SET interval_days=?, ease=?, reps=?, lapses=?, due=?, last_review=? WHERE card_id=?",
        (new.interval, new.ease, new.reps, new.lapses, _d(due), now, card_id),
    )
    conn.execute(
        "INSERT INTO card_reviews(card_id, day, at, rating) VALUES (?,?,?,?)",
        (card_id, _d(day), now, rating),
    )


# ---------- questions and labs ----------

def pick_question(conn, lib: Library, day: date, topic: str | None = None,
                  rng: random.Random | None = None) -> str | None:
    rng = rng or random.Random()
    avail = _available_topics(lib, day)
    qs = [q for q in lib.questions.values()
          if (q.topic == topic if topic else (avail is None or q.topic in avail))]
    if not qs:
        qs = list(lib.questions.values())
    if not qs:
        return None
    last = {}
    for r in conn.execute("SELECT question_id, correct, day FROM question_attempts ORDER BY id"):
        last[r[0]] = (r[1], r[2])
    weights = []
    for q in qs:
        w = 2.0 if q.topic in config.WEAK_TAGS else 1.0
        if q.id not in last:
            w *= 2.0
        else:
            correct, when = last[q.id]
            if when == _d(day):
                w *= 0.05  # avoid repeats within a day
            elif not correct:
                w *= 3.0
        weights.append(w)
    return rng.choices(qs, weights=weights)[0].id


def record_question(conn, qid: str, correct: bool, day: date) -> None:
    conn.execute(
        "INSERT INTO question_attempts(question_id, day, at, correct) VALUES (?,?,?,?)",
        (qid, _d(day), config.now().isoformat(), int(correct)),
    )


def pick_lab(conn, lib: Library, day: date, rng: random.Random | None = None) -> str | None:
    rng = rng or random.Random()
    if not lib.labs:
        return None
    avail = _available_topics(lib, day)
    labs = [l for l in lib.labs.values() if avail is None or l.topic in avail] or list(lib.labs.values())
    last = {r[0]: r[1] for r in conn.execute("SELECT lab_id, MAX(day) FROM lab_attempts GROUP BY lab_id")}
    never = [l for l in labs if l.id not in last]
    if never:
        weak = [l for l in never if l.topic in config.WEAK_TAGS]
        return rng.choice(weak or never).id
    labs.sort(key=lambda l: last[l.id])
    return labs[0].id


def record_lab(conn, lab_id: str, correct: bool, day: date) -> None:
    conn.execute(
        "INSERT INTO lab_attempts(lab_id, day, at, correct) VALUES (?,?,?,?)",
        (lab_id, _d(day), config.now().isoformat(), int(correct)),
    )


# ---------- progress ----------

def progress(conn, lib: Library, day: date) -> list[BlockProgress]:
    mins = minimums(conn, day)
    d = _d(day)
    reviewed = conn.execute("SELECT COUNT(*) FROM card_reviews WHERE day=?", (d,)).fetchone()[0]
    left = cards_remaining(conn, lib, day)
    drill = conn.execute("SELECT COUNT(*) FROM drill_problems WHERE day=? AND given IS NOT NULL", (d,)).fetchone()[0]
    qs = conn.execute("SELECT COUNT(*) FROM question_attempts WHERE day=?", (d,)).fetchone()[0]
    labs = conn.execute("SELECT COUNT(*) FROM lab_attempts WHERE day=?", (d,)).fetchone()[0]
    return [
        BlockProgress("cards", BLOCK_NAMES["cards"], reviewed, reviewed + left, left == 0),
        BlockProgress("drill", BLOCK_NAMES["drill"], drill, mins["drill"], drill >= mins["drill"]),
        BlockProgress("questions", BLOCK_NAMES["questions"], qs, mins["questions"], qs >= mins["questions"]),
        BlockProgress("lab", BLOCK_NAMES["lab"], labs, mins["lab"], labs >= mins["lab"]),
    ]


def current_block(blocks: list[BlockProgress]) -> str | None:
    for b in blocks:
        if not b.complete:
            return b.key
    return None


def update_completion(conn, lib: Library, day: date) -> bool:
    """Marks the day complete once every block is done. Returns True if complete."""
    if is_complete(conn, day):
        return True
    if current_block(progress(conn, lib, day)) is None:
        conn.execute("INSERT OR IGNORE INTO completions(day, at) VALUES (?,?)", (_d(day), config.now().isoformat()))
        return True
    return False


def streak(conn, day: date) -> int:
    done = {r[0] for r in conn.execute("SELECT day FROM completions")}
    d = day if _d(day) in done else day - timedelta(days=1)
    n = 0
    while _d(d) in done:
        n += 1
        d -= timedelta(days=1)
    return n
