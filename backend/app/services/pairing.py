"""Group bulk-uploaded photos into items with obverse/reverse roles.

1. Files whose names end in a role marker (after a separator) are grouped by the rest of the name:
   0042_obv.jpg + 0042_rev.jpg -> one group; 0042-front.png + 0042-back.png -> one group.
2. Remaining files are sorted by name (natural order) and paired in twos: first obverse, second reverse.
   An odd file out becomes a single-photo group.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePath

ROLE_WORDS = {
    "obv": "obverse",
    "obverse": "obverse",
    "o": "obverse",
    "front": "obverse",
    "rev": "reverse",
    "reverse": "reverse",
    "r": "reverse",
    "back": "reverse",
    "edge": "edge",
    "slab": "slab_front",
    "slabfront": "slab_front",
    "slab_front": "slab_front",
    "slab-front": "slab_front",
    "slabback": "slab_back",
    "slab_back": "slab_back",
    "slab-back": "slab_back",
}
_ROLE_ALT = "|".join(sorted((re.escape(w) for w in ROLE_WORDS), key=len, reverse=True))
PATTERN = re.compile(rf"^(?P<key>.+?)[ _.\-](?P<role>{_ROLE_ALT})$", re.IGNORECASE)
ROLE_ORDER = {"obverse": 0, "reverse": 1, "edge": 2, "slab_front": 3, "slab_back": 4, "other": 5}


@dataclass
class PlannedGroup:
    rule: str  # pattern, order, single
    label: str
    members: list[tuple[int, str]] = field(default_factory=list)  # (index into input, role)


def _natural_key(name: str) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def parse_role(filename: str) -> tuple[str, str] | None:
    stem = PurePath(filename).stem
    m = PATTERN.match(stem)
    if not m:
        return None
    return m.group("key"), ROLE_WORDS[m.group("role").lower()]


def plan_groups(filenames: list[str]) -> list[PlannedGroup]:
    keyed: dict[str, PlannedGroup] = {}
    leftovers: list[int] = []
    for idx, name in enumerate(filenames):
        parsed = parse_role(name)
        if parsed is None:
            leftovers.append(idx)
            continue
        key, role = parsed
        norm = key.lower()
        group = keyed.setdefault(norm, PlannedGroup(rule="pattern", label=key))
        if any(r == role for _, r in group.members):
            role = "other"  # duplicate role within a group: keep the file, let the user re-role it
        group.members.append((idx, role))

    groups = list(keyed.values())
    for g in groups:
        g.members.sort(key=lambda m: (ROLE_ORDER[m[1]], m[0]))
        if len(g.members) == 1:
            g.rule = "single"

    leftovers.sort(key=lambda i: _natural_key(filenames[i]))
    for start in range(0, len(leftovers), 2):
        chunk = leftovers[start : start + 2]
        if len(chunk) == 2:
            groups.append(
                PlannedGroup(
                    rule="order",
                    label=PurePath(filenames[chunk[0]]).stem,
                    members=[(chunk[0], "obverse"), (chunk[1], "reverse")],
                )
            )
        else:
            groups.append(
                PlannedGroup(rule="single", label=PurePath(filenames[chunk[0]]).stem, members=[(chunk[0], "obverse")])
            )

    groups.sort(key=lambda g: _natural_key(filenames[g.members[0][0]]))
    return groups
