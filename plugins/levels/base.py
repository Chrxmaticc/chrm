"""Shared bits of the unlock catalogue: the ``Usage`` marker and one row type.

``text.py`` (transforms), ``tools.py`` (generators) and ``content.py`` (text
banks) all hand results back to ``plugin.py`` through these two classes, so they
live here instead of in ``catalog.py`` to avoid an import cycle.
"""
from __future__ import annotations

import hashlib


class Usage(str):
    """A string that should be sent as a warning ("usage: ...")."""


def usage(text: str) -> Usage:
    return Usage(text)


class Unlock:
    """One unlockable command: a name, its level, a description and a runner."""

    __slots__ = ("name", "level", "desc", "run")

    def __init__(self, name: str, level: int, desc: str, run):
        self.name = name
        self.level = level
        self.desc = desc
        self.run = run

    def __repr__(self) -> str:
        return f"<Unlock {self.name} lvl{self.level}>"


def digest(seed: str, value: str, modulo: int) -> int:
    """Stable score for a string, so ``.rate``/``.ship`` do not change per call."""
    raw = hashlib.sha256(f"{seed}|{value.lower().strip()}".encode()).digest()
    return int.from_bytes(raw[:8], "big") % modulo
