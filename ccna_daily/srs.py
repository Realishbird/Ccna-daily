"""Spaced repetition (SM-2 style) with ratings Again=1, Hard=2, Good=3, Easy=4.

Intervals are capped at MAX_INTERVAL days so every card comes back several
times before the exam instead of drifting off for months.
"""
from dataclasses import dataclass
from datetime import date, timedelta

MAX_INTERVAL = 7.0
MIN_EASE = 1.3

AGAIN, HARD, GOOD, EASY = 1, 2, 3, 4


@dataclass
class State:
    interval: float = 0.0
    ease: float = 2.5
    reps: int = 0
    lapses: int = 0


def review(s: State, rating: int, today: date) -> tuple[State, date]:
    s = State(s.interval, s.ease, s.reps, s.lapses)
    if rating == AGAIN:
        if s.reps > 0:
            s.lapses += 1
        s.reps = 0
        s.interval = 0
        s.ease = max(MIN_EASE, s.ease - 0.2)
    elif rating == HARD:
        s.interval = 1 if s.reps == 0 else max(1, s.interval * 1.2)
        s.ease = max(MIN_EASE, s.ease - 0.15)
        s.reps += 1
    elif rating == GOOD:
        if s.reps == 0:
            s.interval = 1
        elif s.reps == 1:
            s.interval = 3
        else:
            s.interval = s.interval * s.ease
        s.reps += 1
    elif rating == EASY:
        s.interval = 3 if s.reps == 0 else s.interval * s.ease * 1.3
        s.ease += 0.15
        s.reps += 1
    else:
        raise ValueError(f"bad rating {rating}")
    s.interval = min(s.interval, MAX_INTERVAL)
    due = today + timedelta(days=round(s.interval))
    return s, due
