"""Loads flash cards, questions, labs and the schedule from YAML files in content/."""
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from . import config

DOMAINS = {
    1: ("Network Fundamentals", 20),
    2: ("Network Access", 20),
    3: ("IP Connectivity", 25),
    4: ("IP Services", 10),
    5: ("Security Fundamentals", 15),
    6: ("Automation and Programmability", 10),
}


@dataclass
class Card:
    id: str
    topic: str
    domain: int
    blueprint: str
    front: str
    back: str


@dataclass
class Question:
    id: str
    topic: str
    domain: int
    blueprint: str
    q: str
    options: list[str]
    answer: list[int]
    explain: str
    exhibit: str = ""

    @property
    def multi(self) -> bool:
        return len(self.answer) > 1


@dataclass
class Lab:
    id: str
    title: str
    topic: str
    domain: int
    blueprint: str
    scenario: str
    outputs: list[dict]
    question: str
    options: list[str]
    answer: int
    explain: str
    topology: str = ""


@dataclass
class Day:
    day: date
    title: str
    topics: list[str]
    kind: str = "study"  # study | review | mock | rest


@dataclass
class Library:
    cards: dict[str, Card] = field(default_factory=dict)
    questions: dict[str, Question] = field(default_factory=dict)
    labs: dict[str, Lab] = field(default_factory=dict)
    schedule: list[Day] = field(default_factory=list)

    def day(self, d: date) -> Day | None:
        for item in self.schedule:
            if item.day == d:
                return item
        return None

    def topic_first_day(self) -> dict[str, date]:
        """Day each topic is first scheduled; unscheduled topics are absent."""
        first: dict[str, date] = {}
        for item in self.schedule:
            for t in item.topics:
                first.setdefault(t, item.day)
        return first

    def topics(self) -> list[str]:
        seen = []
        for c in list(self.cards.values()) + list(self.questions.values()):
            if c.topic not in seen:
                seen.append(c.topic)
        return seen


def _as_list(v) -> list[int]:
    return [int(x) for x in v] if isinstance(v, list) else [int(v)]


def _files(sub: str) -> list[Path]:
    return sorted((config.CONTENT_DIR / sub).glob("*.yaml"))


def load() -> Library:
    lib = Library()
    for path in _files("cards"):
        doc = yaml.safe_load(path.read_text())
        for c in doc["cards"]:
            card = Card(
                id=c["id"],
                topic=c.get("topic", doc["topic"]),
                domain=int(c.get("domain", doc["domain"])),
                blueprint=str(c.get("blueprint", doc.get("blueprint", ""))),
                front=c["front"].strip(),
                back=c["back"].strip(),
            )
            if card.id in lib.cards:
                raise ValueError(f"duplicate card id {card.id} in {path}")
            lib.cards[card.id] = card
    for path in _files("questions"):
        doc = yaml.safe_load(path.read_text())
        for q in doc["questions"]:
            question = Question(
                id=q["id"],
                topic=q.get("topic", doc["topic"]),
                domain=int(q.get("domain", doc["domain"])),
                blueprint=str(q.get("blueprint", doc.get("blueprint", ""))),
                q=q["q"].strip(),
                options=[str(o) for o in q["options"]],
                answer=_as_list(q["answer"]),
                explain=q["explain"].strip(),
                exhibit=(q.get("exhibit") or "").rstrip(),
            )
            if question.id in lib.questions:
                raise ValueError(f"duplicate question id {question.id} in {path}")
            if any(a >= len(question.options) for a in question.answer):
                raise ValueError(f"answer out of range in {question.id}")
            lib.questions[question.id] = question
    for path in _files("labs"):
        doc = yaml.safe_load(path.read_text())
        for l in doc["labs"]:
            lab = Lab(
                id=l["id"],
                title=l["title"],
                topic=l.get("topic", doc.get("topic", "")),
                domain=int(l.get("domain", doc.get("domain", 3))),
                blueprint=str(l.get("blueprint", "")),
                scenario=l["scenario"].strip(),
                topology=(l.get("topology") or "").rstrip(),
                outputs=l["outputs"],
                question=l["question"].strip(),
                options=[str(o) for o in l["options"]],
                answer=int(l["answer"]),
                explain=l["explain"].strip(),
            )
            if lab.id in lib.labs:
                raise ValueError(f"duplicate lab id {lab.id} in {path}")
            lib.labs[lab.id] = lab
    sched = config.CONTENT_DIR / "schedule.yaml"
    if sched.exists():
        doc = yaml.safe_load(sched.read_text())
        for d in doc["days"]:
            lib.schedule.append(
                Day(
                    day=date.fromisoformat(str(d["date"])),
                    title=d["title"],
                    topics=d.get("topics", []),
                    kind=d.get("kind", "study"),
                )
            )
        lib.schedule.sort(key=lambda x: x.day)
    return lib
