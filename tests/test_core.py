import ipaddress
import random
from datetime import date, datetime, time

import pytest

from ccna_daily import config, content, srs, subnet


# ---------- subnetting generator ----------

@pytest.mark.parametrize("kind", subnet.KINDS)
def test_generated_answers_check_against_themselves(kind):
    rng = random.Random(1)
    for _ in range(300):
        p = subnet.generate(kind, rng)
        assert subnet.check(p.kind, p.answer, p.answer), p


def test_network_and_broadcast_are_correct():
    rng = random.Random(7)
    for _ in range(500):
        p = subnet.generate("network", rng)
        cidr = p.prompt.split(" of ")[1].rstrip("?")
        assert p.answer == str(ipaddress.ip_interface(cidr).network.network_address)
        p = subnet.generate("broadcast", rng)
        cidr = p.prompt.split(" of ")[1].rstrip("?")
        assert p.answer == str(ipaddress.ip_interface(cidr).network.broadcast_address)


def test_prefix_for_hosts_is_smallest():
    rng = random.Random(3)
    for _ in range(500):
        p = subnet.generate("prefix_for_hosts", rng)
        hosts = int(p.prompt.split("fits ")[1].split(" ")[0])
        prefix = int(p.answer.lstrip("/"))
        assert 2 ** (32 - prefix) - 2 >= hosts
        if prefix < 30:
            assert 2 ** (32 - prefix - 1) - 2 < hosts


def test_same_subnet_answer():
    rng = random.Random(5)
    seen = set()
    for _ in range(300):
        p = subnet.generate("same_subnet", rng)
        words = p.prompt.split()
        a, b, plen = words[1], words[3], int(words[-2].lstrip("/"))
        same = ipaddress.ip_interface(f"{a}/{plen}").network == ipaddress.ip_interface(f"{b}/{plen}").network
        assert p.answer == ("yes" if same else "no")
        seen.add(p.answer)
    assert seen == {"yes", "no"}


def test_check_accepts_reasonable_formats():
    assert subnet.check("prefix_for_hosts", "/26", "26")
    assert subnet.check("prefix_for_hosts", "/26", " /26 ")
    assert subnet.check("first_last", "10.0.0.1 - 10.0.0.14", "10.0.0.1 10.0.0.14")
    assert subnet.check("first_last", "10.0.0.1 - 10.0.0.14", "10.0.0.1-10.0.0.14")
    assert not subnet.check("first_last", "10.0.0.1 - 10.0.0.14", "10.0.0.14 - 10.0.0.1")
    assert subnet.check("same_subnet", "yes", "Y")
    assert subnet.check("hosts", "1022", "1,022")
    assert subnet.check("ipv6_prefix", "2001:db8:1::/48", "2001:0db8:0001::/48")
    assert not subnet.check("ipv6_compress", "2001:db8::1", "2001:0db8::1")
    assert not subnet.check("network", "10.0.0.0", "banana")
    assert not subnet.check("network", "10.0.0.0", "")


# ---------- spaced repetition ----------

def test_srs_progression_and_cap():
    d = date(2026, 11, 6)
    s = srs.State()
    s, due = srs.review(s, srs.GOOD, d)
    assert (due - d).days == 1
    s, due = srs.review(s, srs.GOOD, d)
    assert (due - d).days == 3
    for _ in range(5):
        s, due = srs.review(s, srs.EASY, d)
    assert (due - d).days <= srs.MAX_INTERVAL
    s, due = srs.review(s, srs.AGAIN, d)
    assert due == d and s.lapses == 1 and s.reps == 0


# ---------- content ----------

def test_content_loads_and_is_consistent():
    lib = content.load()
    assert len(lib.cards) >= 100
    assert len(lib.questions) >= 30
    assert len(lib.labs) >= 5
    for q in lib.questions.values():
        assert q.domain in content.DOMAINS
        assert all(0 <= a < len(q.options) for a in q.answer)
        assert len(set(q.options)) == len(q.options), q.id
    for l in lib.labs.values():
        assert 0 <= l.answer < len(l.options)
        assert l.outputs
    # Every content topic should be scheduled somewhere.
    scheduled = lib.topic_first_day()
    for t in lib.topics():
        assert t in scheduled, f"topic {t} not in schedule"
    assert lib.schedule[0].day == config.START_DATE
