"""CCNA Daily web app."""
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import timedelta
from urllib.parse import urlencode

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import config, content, db, reminders, session, subnet
from .content import DOMAINS

logging.basicConfig(level=logging.INFO)

HERE = config.ROOT / "ccna_daily"
LIB = content.Library()


def lib() -> content.Library:
    return LIB


@asynccontextmanager
async def lifespan(app: FastAPI):
    global LIB
    db.init()
    LIB = content.load()
    task = asyncio.create_task(reminders.loop(lib))
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.globals["DOMAINS"] = DOMAINS


def render(request: Request, name: str, **ctx) -> HTMLResponse:
    day = config.today()
    with db.get() as conn:
        ctx.setdefault("streak", session.streak(conn, day))
        ctx.setdefault("day_complete", session.is_complete(conn, day))
    ctx.setdefault("nav", "")
    return templates.TemplateResponse(request, name, {"today": day, **ctx})


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def gate(conn, block: str) -> RedirectResponse | None:
    """Blocks run in order until the day is done. After that everything is open."""
    day = config.today()
    if session.is_complete(conn, day):
        return None
    blocks = session.progress(conn, LIB, day)
    for b in blocks:
        if b.key == block:
            return None
        if not b.complete:
            return redirect(f"/{b.key}")
    return None


def _qs(**kw) -> str:
    kw = {k: v for k, v in kw.items() if v}
    return ("?" + urlencode(kw)) if kw else ""


# ---------- home ----------

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    day = config.today()
    with db.get() as conn:
        complete = session.update_completion(conn, LIB, day)
        blocks = session.progress(conn, LIB, day)
        current = session.current_block(blocks)
        checkin = conn.execute("SELECT * FROM checkins WHERE day=?", (day.isoformat(),)).fetchone()
        carry = session.missed_yesterday(conn, day)
        done_days = {r[0] for r in conn.execute("SELECT day FROM completions")}
    week = []
    for i in range(6, -1, -1):
        d = day - timedelta(days=i)
        status = "done" if d.isoformat() in done_days else ("today" if d == day else
                 ("missed" if d >= config.START_DATE else "none"))
        week.append({"d": d, "status": status})
    sched = LIB.day(day)
    upcoming = [s for s in LIB.schedule if s.day > day][:3]
    exam_days_left = (LIB.schedule[-1].day - day).days if LIB.schedule else None
    return render(request, "home.html", nav="home", blocks=blocks, current=current, complete=complete,
                  checkin=checkin, sched=sched, upcoming=upcoming, week=week, carry=carry,
                  days_left=exam_days_left)


@app.post("/checkin")
def checkin(sleep: float = Form(0), exercise: int = Form(0), water: int = Form(0)):
    with db.get() as conn:
        conn.execute("INSERT OR REPLACE INTO checkins(day, sleep, exercise, water) VALUES (?,?,?,?)",
                     (config.today().isoformat(), sleep, exercise, water))
    return redirect("/")


# ---------- cards ----------

@app.get("/cards", response_class=HTMLResponse)
def cards(request: Request, topic: str = "", extra: int = 0):
    day = config.today()
    with db.get() as conn:
        if not extra and (r := gate(conn, "cards")):
            return r
        if extra and not session.is_complete(conn, day):
            return redirect("/cards")
        cid = session.next_card(conn, LIB, day, extra_topic=topic or None, extra=bool(extra))
        state = conn.execute("SELECT * FROM card_state WHERE card_id=?", (cid,)).fetchone() if cid else None
        remaining = session.cards_remaining(conn, LIB, day)
        reviewed = conn.execute("SELECT COUNT(*) FROM card_reviews WHERE day=?", (day.isoformat(),)).fetchone()[0]
        if cid is None:
            session.update_completion(conn, LIB, day)
    if cid is None:
        if extra:
            return render(request, "message.html", title="Topic finished",
                          body="No more cards for this topic right now. Pick another in Extra practice.",
                          link="/extra", link_text="Extra practice")
        return redirect("/")
    card = LIB.cards[cid]
    return render(request, "cards.html", nav="study", card=card, is_new=state["reps"] == 0 and state["last_review"] is None,
                  remaining=remaining, reviewed=reviewed, topic=topic, extra=extra)


@app.post("/cards/{card_id}/rate")
def rate(card_id: str, rating: int = Form(...), topic: str = Form(""), extra: int = Form(0)):
    if card_id not in LIB.cards or rating not in (1, 2, 3, 4):
        raise HTTPException(400)
    with db.get() as conn:
        session.rate_card(conn, card_id, rating, config.today())
    return redirect("/cards" + _qs(topic=topic, extra=extra))


# ---------- subnetting drill ----------

def _drill_stats(conn, day):
    rows = conn.execute("SELECT correct, seconds FROM drill_problems WHERE day=? AND given IS NOT NULL ORDER BY id",
                        (day.isoformat(),)).fetchall()
    n = len(rows)
    right = sum(r["correct"] for r in rows)
    avg = sum(r["seconds"] for r in rows if r["correct"]) / right if right else 0
    run = best = 0
    for r in rows:
        run = run + 1 if r["correct"] else 0
        best = max(best, run)
    best_avg = conn.execute(
        "SELECT MIN(a) FROM (SELECT AVG(seconds) a, COUNT(*) n FROM drill_problems "
        "WHERE correct=1 GROUP BY day HAVING n>=10)").fetchone()[0]
    return {"n": n, "right": right, "acc": round(100 * right / n) if n else 0, "avg": avg,
            "best_run": best, "best_avg": best_avg}


@app.get("/drill", response_class=HTMLResponse)
def drill(request: Request, last: int = 0):
    day = config.today()
    with db.get() as conn:
        if r := gate(conn, "drill"):
            return r
        prev = conn.execute("SELECT * FROM drill_problems WHERE id=?", (last,)).fetchone() if last else None
        pending = conn.execute(
            "SELECT * FROM drill_problems WHERE day=? AND given IS NULL ORDER BY id DESC LIMIT 1",
            (day.isoformat(),)).fetchone()
        if pending is None:
            p = subnet.generate()
            cur = conn.execute(
                "INSERT INTO drill_problems(day, kind, prompt, answer, issued_at) VALUES (?,?,?,?,?)",
                (day.isoformat(), p.kind, p.prompt, p.answer, config.now().isoformat()))
            pending = conn.execute("SELECT * FROM drill_problems WHERE id=?", (cur.lastrowid,)).fetchone()
        else:
            # Restart the clock when the problem is shown again, so time away does not count.
            conn.execute("UPDATE drill_problems SET issued_at=? WHERE id=?", (config.now().isoformat(), pending["id"]))
            pending = conn.execute("SELECT * FROM drill_problems WHERE id=?", (pending["id"],)).fetchone()
        stats = _drill_stats(conn, day)
        need = session.minimums(conn, day)["drill"]
        session.update_completion(conn, LIB, day)
    hint = subnet.HINTS.get(pending["kind"], "")
    return render(request, "drill.html", nav="study", problem=pending, prev=prev, stats=stats, need=need, hint=hint)


@app.post("/drill/{pid}")
def drill_answer(pid: int, given: str = Form("")):
    now = config.now()
    with db.get() as conn:
        row = conn.execute("SELECT * FROM drill_problems WHERE id=?", (pid,)).fetchone()
        if row is None:
            raise HTTPException(404)
        if row["given"] is None:
            from datetime import datetime
            secs = (now - datetime.fromisoformat(row["issued_at"])).total_seconds()
            ok = subnet.check(row["kind"], row["answer"], given)
            conn.execute("UPDATE drill_problems SET given=?, correct=?, seconds=? WHERE id=?",
                         (given.strip() or "(blank)", int(ok), round(secs, 1), pid))
            session.update_completion(conn, LIB, config.today())
    return redirect(f"/drill?last={pid}")


# ---------- practice questions ----------

@app.get("/questions")
def questions(topic: str = ""):
    with db.get() as conn:
        if not topic and (r := gate(conn, "questions")):
            return r
        if topic and not session.is_complete(conn, config.today()):
            return redirect("/questions")
        qid = session.pick_question(conn, LIB, config.today(), topic=topic or None)
    if qid is None:
        return redirect("/")
    return redirect(f"/questions/{qid}" + _qs(topic=topic))


def _q_counts(conn):
    day = config.today()
    done = conn.execute("SELECT COUNT(*), COALESCE(SUM(correct),0) FROM question_attempts WHERE day=?",
                        (day.isoformat(),)).fetchone()
    return done[0], done[1], session.minimums(conn, day)["questions"]


@app.get("/questions/{qid}", response_class=HTMLResponse)
def question(request: Request, qid: str, topic: str = "", a: str = ""):
    q = LIB.questions.get(qid)
    if q is None:
        raise HTTPException(404)
    chosen = [int(x) for x in a.split(",") if x.isdigit()] if a else None
    with db.get() as conn:
        n, right, need = _q_counts(conn)
    return render(request, "question.html", nav="study", q=q, chosen=chosen, topic=topic,
                  n=n, right=right, need=need,
                  correct=(sorted(chosen) == sorted(q.answer)) if chosen is not None else None)


@app.post("/questions/{qid}")
async def answer_question(request: Request, qid: str):
    q = LIB.questions.get(qid)
    if q is None:
        raise HTTPException(404)
    form = await request.form()
    chosen = sorted({int(v) for v in form.getlist("opt") if str(v).isdigit()})
    topic = form.get("topic", "")
    if not chosen:
        return redirect(f"/questions/{qid}" + _qs(topic=topic))
    with db.get() as conn:
        session.record_question(conn, qid, chosen == sorted(q.answer), config.today())
        session.update_completion(conn, LIB, config.today())
    return redirect(f"/questions/{qid}" + _qs(topic=topic, a=",".join(map(str, chosen))))


# ---------- troubleshooting labs ----------

@app.get("/lab")
def lab_pick(any: int = 0):
    with db.get() as conn:
        if r := gate(conn, "lab"):
            return r
        lid = session.pick_lab(conn, LIB, config.today())
    if lid is None:
        return redirect("/")
    return redirect(f"/lab/{lid}")


@app.get("/lab/{lid}", response_class=HTMLResponse)
def lab(request: Request, lid: str, a: int = -1):
    l = LIB.labs.get(lid)
    if l is None:
        raise HTTPException(404)
    return render(request, "lab.html", nav="study", lab=l, chosen=a if a >= 0 else None)


@app.post("/lab/{lid}")
def lab_answer(lid: str, opt: int = Form(...)):
    l = LIB.labs.get(lid)
    if l is None:
        raise HTTPException(404)
    with db.get() as conn:
        session.record_lab(conn, lid, opt == l.answer, config.today())
        session.update_completion(conn, LIB, config.today())
    return redirect(f"/lab/{lid}?a={opt}")


# ---------- extra practice ----------

@app.get("/extra", response_class=HTMLResponse)
def extra(request: Request):
    day = config.today()
    with db.get() as conn:
        if not session.is_complete(conn, day):
            return render(request, "message.html", nav="extra", title="Finish today's session first",
                          body="Extra practice opens once today's required session is done.",
                          link="/", link_text="Back to today")
        known = {r[0] for r in conn.execute("SELECT card_id FROM card_state")}
        acc = {}
        for r in conn.execute("SELECT question_id, correct FROM question_attempts"):
            t = LIB.questions[r[0]].topic if r[0] in LIB.questions else None
            if t:
                a = acc.setdefault(t, [0, 0])
                a[0] += r[1]
                a[1] += 1
    first = LIB.topic_first_day()
    topics = []
    for t in LIB.topics():
        cs = [c for c in LIB.cards.values() if c.topic == t]
        domain = (cs[0].domain if cs else next((q.domain for q in LIB.questions.values() if q.topic == t), 0))
        topics.append({
            "topic": t, "domain": domain, "first": first.get(t),
            "cards": len(cs), "learned": sum(1 for c in cs if c.id in known),
            "questions": sum(1 for q in LIB.questions.values() if q.topic == t),
            "acc": round(100 * acc[t][0] / acc[t][1]) if t in acc and acc[t][1] else None,
            "weak": t in config.WEAK_TAGS,
        })
    topics.sort(key=lambda x: (x["first"] or day + timedelta(days=999), x["topic"]))
    return render(request, "extra.html", nav="extra", topics=topics)


# ---------- stats ----------

@app.get("/stats", response_class=HTMLResponse)
def stats(request: Request):
    day = config.today()
    with db.get() as conn:
        done_days = {r[0] for r in conn.execute("SELECT day FROM completions")}
        cal = []
        start = min(config.START_DATE, day) - timedelta(days=(min(config.START_DATE, day).weekday()))
        end = max(day, LIB.schedule[-1].day if LIB.schedule else day)
        d = start
        while d <= end:
            s = d.isoformat()
            status = ("done" if s in done_days else "today" if d == day else
                      "missed" if config.START_DATE <= d < day else "future" if d > day else "none")
            cal.append({"d": d, "status": status})
            d += timedelta(days=1)
        drill = conn.execute(
            "SELECT day, COUNT(*) n, SUM(correct) r, AVG(CASE WHEN correct=1 THEN seconds END) t "
            "FROM drill_problems WHERE given IS NOT NULL GROUP BY day ORDER BY day DESC LIMIT 14").fetchall()
        kinds = conn.execute(
            "SELECT kind, COUNT(*) n, SUM(correct) r, AVG(CASE WHEN correct=1 THEN seconds END) t "
            "FROM drill_problems WHERE given IS NOT NULL GROUP BY kind ORDER BY 1.0*SUM(correct)/COUNT(*)").fetchall()
        dom = {k: [0, 0] for k in DOMAINS}
        for r in conn.execute("SELECT question_id, correct FROM question_attempts"):
            q = LIB.questions.get(r[0])
            if q:
                dom[q.domain][0] += r[1]
                dom[q.domain][1] += 1
        card_rows = conn.execute("SELECT reps, interval_days FROM card_state").fetchall()
        checkins = conn.execute("SELECT * FROM checkins ORDER BY day DESC LIMIT 7").fetchall()
    mature = sum(1 for r in card_rows if r["interval_days"] >= 3)
    learning = len(card_rows) - mature
    domains = [{"n": k, "name": v[0], "weight": v[1], "right": dom[k][0], "total": dom[k][1],
                "acc": round(100 * dom[k][0] / dom[k][1]) if dom[k][1] else None} for k, v in DOMAINS.items()]
    return render(request, "stats.html", nav="stats", cal=cal, drill=drill, kinds=kinds, domains=domains,
                  mature=mature, learning=learning, total_cards=len(LIB.cards),
                  checkins=checkins, kind_names=subnet.NAMES)


@app.get("/healthz")
def healthz():
    return {"ok": True, "cards": len(LIB.cards), "questions": len(LIB.questions), "labs": len(LIB.labs)}
