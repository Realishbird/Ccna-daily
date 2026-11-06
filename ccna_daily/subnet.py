"""Random subnetting and IPv6 problems with answer checking."""
import ipaddress
import random
import re
from dataclasses import dataclass

KINDS = [
    "network", "broadcast", "first_last", "hosts", "prefix_for_hosts",
    "mask", "mask_to_prefix", "wildcard", "subnet_count", "same_subnet",
    "ipv6_compress", "ipv6_prefix",
]

# How often each kind is picked. IPv4 subnet math dominates, like the exam.
WEIGHTS = {
    "network": 3, "broadcast": 3, "first_last": 3, "hosts": 2,
    "prefix_for_hosts": 2, "mask": 1, "mask_to_prefix": 1, "wildcard": 2,
    "subnet_count": 2, "same_subnet": 2, "ipv6_compress": 1, "ipv6_prefix": 1,
}


NAMES = {
    "network": "Network address", "broadcast": "Broadcast address", "first_last": "First/last host",
    "hosts": "Hosts per prefix", "prefix_for_hosts": "Prefix for N hosts", "mask": "Prefix to mask",
    "mask_to_prefix": "Mask to prefix", "wildcard": "Wildcard mask", "subnet_count": "Subnet count",
    "same_subnet": "Same subnet?", "ipv6_compress": "IPv6 shortening", "ipv6_prefix": "IPv6 prefix",
}

HINTS = {
    "first_last": "Type both, e.g. 10.0.0.1 - 10.0.0.14",
    "same_subnet": "yes or no",
    "ipv6_prefix": "e.g. 2001:db8:1::/48",
    "ipv6_compress": "Lowercase, :: for the longest zero run, drop leading zeros",
    "prefix_for_hosts": "e.g. /26",
    "mask_to_prefix": "e.g. /26",
}


@dataclass
class Problem:
    kind: str
    prompt: str
    answer: str
    hint: str = ""


def _rand_ipv4(rng: random.Random) -> ipaddress.IPv4Address:
    block = rng.choice(["10", "172", "192"])
    if block == "10":
        return ipaddress.IPv4Address(f"10.{rng.randint(0,255)}.{rng.randint(0,255)}.{rng.randint(1,254)}")
    if block == "172":
        return ipaddress.IPv4Address(f"172.{rng.randint(16,31)}.{rng.randint(0,255)}.{rng.randint(1,254)}")
    return ipaddress.IPv4Address(f"192.168.{rng.randint(0,255)}.{rng.randint(1,254)}")


def _rand_prefix(rng: random.Random) -> int:
    # Mostly /20-/30, sometimes /16-/19.
    return rng.choice([16, 17, 18, 19] + list(range(20, 31)) * 3)


def _host_iface(rng: random.Random) -> ipaddress.IPv4Interface:
    """An address that is a usable host (not network or broadcast)."""
    while True:
        iface = ipaddress.IPv4Interface(f"{_rand_ipv4(rng)}/{_rand_prefix(rng)}")
        net = iface.network
        if iface.ip not in (net.network_address, net.broadcast_address):
            return iface


def _mask(prefix: int) -> str:
    return str(ipaddress.IPv4Network(f"0.0.0.0/{prefix}").netmask)


def _wildcard(prefix: int) -> str:
    return str(ipaddress.IPv4Network(f"0.0.0.0/{prefix}").hostmask)


def _rand_ipv6(rng: random.Random) -> ipaddress.IPv6Address:
    groups = ["2001", "db8"] + [f"{rng.randint(0, 0xffff):x}" for _ in range(6)]
    # Zero out a run of groups and a few single groups so compression matters.
    start = rng.randint(2, 6)
    for i in range(start, min(8, start + rng.randint(1, 3))):
        groups[i] = "0"
    for _ in range(rng.randint(0, 2)):
        groups[rng.randint(2, 7)] = "0"
    return ipaddress.IPv6Address(":".join(groups))


def generate(kind: str | None = None, rng: random.Random | None = None) -> Problem:
    rng = rng or random.Random()
    if kind is None:
        kind = rng.choices(KINDS, weights=[WEIGHTS[k] for k in KINDS])[0]
    if kind == "network":
        i = _host_iface(rng)
        return Problem(kind, f"Network address of {i.with_prefixlen}?", str(i.network.network_address))
    if kind == "broadcast":
        i = _host_iface(rng)
        return Problem(kind, f"Broadcast address of {i.with_prefixlen}?", str(i.network.broadcast_address))
    if kind == "first_last":
        i = _host_iface(rng)
        n = i.network
        first = n.network_address + 1
        last = n.broadcast_address - 1
        return Problem(kind, f"First and last usable host of {i.with_prefixlen}?", f"{first} - {last}",
                       hint="Type both, e.g. 10.0.0.1 - 10.0.0.14")
    if kind == "hosts":
        p = rng.randint(20, 30)
        return Problem(kind, f"How many usable hosts in a /{p}?", str(2 ** (32 - p) - 2))
    if kind == "prefix_for_hosts":
        p = rng.randint(20, 30)
        lo = 2 ** (32 - p - 1) - 2 + 1 if p < 30 else 1
        hosts = rng.randint(max(lo, 1), 2 ** (32 - p) - 2)
        return Problem(kind, f"Smallest prefix that fits {hosts} hosts in one subnet?", f"/{p}")
    if kind == "mask":
        p = rng.randint(16, 30)
        return Problem(kind, f"Dotted-decimal mask for /{p}?", _mask(p))
    if kind == "mask_to_prefix":
        p = rng.randint(16, 30)
        return Problem(kind, f"Prefix length of mask {_mask(p)}?", f"/{p}")
    if kind == "wildcard":
        p = rng.randint(16, 30)
        return Problem(kind, f"Wildcard mask for /{p} (as used in ACLs and OSPF)?", _wildcard(p))
    if kind == "subnet_count":
        big = rng.choice([16, 20, 22, 23, 24, 24, 24])
        small = rng.randint(big + 1, min(30, big + 8))
        return Problem(kind, f"How many /{small} subnets fit in one /{big}?", str(2 ** (small - big)))
    if kind == "same_subnet":
        i = _host_iface(rng)
        net = i.network
        if rng.random() < 0.5 and net.num_addresses > 4:
            other = net.network_address + rng.randint(1, net.num_addresses - 2)
        else:
            nxt = ipaddress.IPv4Network(f"{net.broadcast_address + 1}/{net.prefixlen}", strict=False) \
                if int(net.broadcast_address) < 0xFFFFFFF0 else net
            other = nxt.network_address + rng.randint(1, max(1, nxt.num_addresses - 2))
        same = ipaddress.IPv4Interface(f"{other}/{net.prefixlen}").network == net
        return Problem(kind, f"Are {i.ip} and {other} in the same subnet with a /{net.prefixlen} mask?",
                       "yes" if same else "no", hint="yes or no")
    if kind == "ipv6_compress":
        a = _rand_ipv6(rng)
        return Problem(kind, f"Shortest form of {a.exploded}?", a.compressed)
    if kind == "ipv6_prefix":
        a = _rand_ipv6(rng)
        p = rng.choice([48, 56, 64, 64, 64])
        net = ipaddress.IPv6Network(f"{a}/{p}", strict=False)
        return Problem(kind, f"Network prefix of {a.compressed}/{p}?", net.compressed,
                       hint="e.g. 2001:db8:1::/48")
    raise ValueError(f"unknown kind {kind}")


_IPV4 = re.compile(r"\d{1,3}(?:\.\d{1,3}){3}")


def check(kind: str, answer: str, given: str) -> bool:
    g = given.strip().lower()
    if not g:
        return False
    try:
        if kind in ("network", "broadcast", "mask", "wildcard"):
            return ipaddress.IPv4Address(g) == ipaddress.IPv4Address(answer)
        if kind == "first_last":
            want = _IPV4.findall(answer)
            got = _IPV4.findall(g)
            return len(got) == 2 and [ipaddress.IPv4Address(x) for x in got] == [ipaddress.IPv4Address(x) for x in want]
        if kind in ("prefix_for_hosts", "mask_to_prefix"):
            return g.lstrip("/") == answer.lstrip("/")
        if kind in ("hosts", "subnet_count"):
            return int(g.replace(",", "")) == int(answer)
        if kind == "same_subnet":
            return g[:1] == answer[:1]
        if kind == "ipv6_compress":
            # Must be the shortest (RFC 5952) form, not just an equal address.
            return g == answer
        if kind == "ipv6_prefix":
            return ipaddress.IPv6Network(g) == ipaddress.IPv6Network(answer)
    except ValueError:
        return False
    return False
