import re
from datetime import date, datetime, time, timedelta

import pytest
from fastapi.testclient import TestClient

from ccna_daily import config, db, reminders


@pytest.fixture
def clock(monkeypatch):
    state = {"now": datetime(2026, 11, 6, 9, 0, tzinfo=config.TZ)}
    monkeypatch.setattr(config, "now", lambda: state["now"])
    monkeypatch.setattr(config, "today", lambda: state["now"].date())
    return state


@pytest.fixture
def client(tmp_path, monkeypatch, clock):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "NEW_CARDS_PER_DAY", 5)
    monkeypatch.setattr(config, "DRILL_MIN", 3)
    monkeypatch.setattr(config, "QUESTIONS_MIN", 3)
    from ccna_daily import app as app_module
    with TestClient(app_module.app) as c:
        yield c


def _card_id(html):
    return re.search(r'action="/cards/([^/]+)/rate"', html).group(1)


def do_cards(c):
    for _ in range(100):
        r = c.get("/cards")
        if r.url.path != "/cards":
            return
        c.post(f"/cards/{_card_id(r.text)}/rate", data={"rating": 3})
    raise AssertionError("cards never finished")


def do_drill(c, n, correct=True):
    from ccna_daily import db as dbm
    for _ in range(n):
        r = c.get("/drill")
        assert r.url.path == "/drill"
        pid = int(re.search(r'action="/drill/(\d+)"', r.text).group(1))
        with dbm.get() as conn:
            ans = conn.execute("SELECT answer FROM drill_problems WHERE id=?", (pid,)).fetchone()[0]
        c.post(f"/drill/{pid}", data={"given": ans if correct else "nope"})


def do_questions(c, n):
    from ccna_daily import app as app_module
    for _ in range(n):
        r = c.get("/questions")
        assert r.url.path.startswith("/questions/"), r.url
        qid = r.url.path.rsplit("/", 1)[1]
        q = app_module.LIB.questions[qid]
        c.post(f"/questions/{qid}", data={"opt": [str(a) for a in q.answer]})


def do_lab(c):
    from ccna_daily import app as app_module
    r = c.get("/lab")
    assert r.url.path.startswith("/lab/")
    lid = r.url.path.rsplit("/", 1)[1]
    c.post(f"/lab/{lid}", data={"opt": app_module.LIB.labs[lid].answer})


def test_home_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Flash cards" in r.text and "Subnetting drill" in r.text


def test_blocks_are_gated_in_order(client):
    assert client.get("/drill").url.path == "/cards"
    assert client.get("/questions").url.path == "/cards"
    assert client.get("/lab").url.path == "/cards"
    assert "Finish today" in client.get("/extra").text


def test_full_day_flow_completes_and_unlocks_extra(client, clock):
    do_cards(client)
    assert client.get("/questions").url.path == "/drill"
    do_drill(client, 3)
    assert client.get("/lab").url.path.startswith("/questions/")
    do_questions(client, 3)
    do_lab(client)
    home = client.get("/").text
    assert "Today's session is done" in home
    extra = client.get("/extra")
    assert "Study a topic" in extra.text
    # Study ahead: pull cards from a topic scheduled later.
    r = client.get("/cards", params={"extra": 1, "topic": "ospf"})
    assert r.status_code == 200 and "ospf" in r.text
    # Extra drills keep working after completion.
    assert client.get("/drill").url.path == "/drill"
    assert client.get("/stats").status_code == 200


def test_streak_and_missed_day_carryover(client, clock):
    def full_day():
        do_cards(client)
        do_drill(client, config.DRILL_MIN * 2)
        do_questions(client, config.QUESTIONS_MIN * 2)
        do_lab(client)
    full_day()
    clock["now"] += timedelta(days=1)
    full_day()
    assert '<b>2</b>' in client.get("/").text
    # Skip a day: the next day shows the carry-over banner and bigger minimums.
    clock["now"] += timedelta(days=2)
    home = client.get("/").text
    assert "Yesterday was missed" in home
    from ccna_daily import session
    with db.get() as conn:
        assert session.minimums(conn, config.today())["drill"] == round(config.DRILL_MIN * 1.5)


def test_question_feedback_page(client, clock):
    from ccna_daily import app as app_module
    qid = next(iter(app_module.LIB.questions))
    q = app_module.LIB.questions[qid]
    wrong = next(i for i in range(len(q.options)) if i not in q.answer)
    r = client.post(f"/questions/{qid}", data={"opt": str(wrong)})
    assert "Incorrect" in r.text and q.explain[:20] in r.text.replace("&#39;", "'").replace("&quot;", '"')


def test_reminder_slots(client, clock, monkeypatch):
    from ccna_daily import app as app_module
    lib = app_module.LIB
    clock["now"] = datetime(2026, 11, 6, 11, 0, tzinfo=config.TZ)
    assert reminders.due_slot(lib, clock["now"]) is None
    clock["now"] = datetime(2026, 11, 6, 12, 1, tzinfo=config.TZ)
    assert reminders.due_slot(lib, clock["now"]) == "12:00"
    assert reminders.due_slot(lib, clock["now"]) is None  # only once
    clock["now"] = datetime(2026, 11, 6, 19, 5, tzinfo=config.TZ)
    assert reminders.due_slot(lib, clock["now"]) == "19:00"
    msg = reminders.message_for(lib)
    assert "not done" in msg
    # A completed day sends nothing.
    clock["now"] = datetime(2026, 11, 7, 8, 0, tzinfo=config.TZ)
    with db.get() as conn:
        conn.execute("INSERT INTO completions(day, at) VALUES ('2026-11-07', 'x')")
    clock["now"] = datetime(2026, 11, 7, 12, 30, tzinfo=config.TZ)
    assert reminders.due_slot(lib, clock["now"]) is None


def test_late_restart_sends_one_reminder(client, clock):
    from ccna_daily import app as app_module
    clock["now"] = datetime(2026, 11, 6, 20, 0, tzinfo=config.TZ)
    assert reminders.due_slot(app_module.LIB, clock["now"]) == "19:00"
    assert reminders.due_slot(app_module.LIB, clock["now"]) is None
