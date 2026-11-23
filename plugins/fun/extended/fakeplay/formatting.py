"""Progress text for presences: ``.fakeplay celeste | 52%``.

Discord's activity payload has no percentage field, so the only place a number
like "52%" can live is the free-text ``details``/``state`` pair. Two things make
that useful:

* a line that is *only* a percentage is expanded into a bar (``█████░░░░░ 52%``);
* ``52% in 30m`` additionally sets the activity's end timestamp, and then the
  client draws its own moving progress bar with the remaining time.

Everything here is pure: the command keeps the presence plumbing, this module
keeps the parsing so it can be tested without a gateway connection.
"""
import re

#: ``52%``, ``52.5 % in 30m`` -- the "in <duration>" tail is optional
PROGRESS_RE = re.compile(
    r"^(?P<pct>\d{1,3}(?:\.\d+)?)\s*%\s*(?:in\s+(?P<eta>.+))?$",
    re.IGNORECASE,
)

#: a percentage line, so a bad duration gets reported instead of silently
#: rendering as literal text. Text like ``50% off everything`` is not progress
#: and stays literal; ``52% in banana`` is, and gets an error.
_PREFIX_RE = re.compile(r"^\s*\d+(?:\.\d+)?\s*%\s*(?:in\b.*)?$", re.IGNORECASE)

FILLED = "\u2588"  # █
EMPTY = "\u2591"  # ░
WIDTH = 10

_UNITS = {"s": 1.0, "m": 60.0, "h": 3600.0}


def parse_duration(raw):
    """``30m`` / ``90s`` / ``1.5h`` -> seconds. Raises ``ValueError``."""
    text = (raw or "").strip().lower()
    if not text or text[-1] not in _UNITS:
        raise ValueError("duration needs a unit, like `30m`, `90s` or `1.5h`")
    return float(text[:-1]) * _UNITS[text[-1]]


def parse_progress(raw):
    """``"52%"`` -> ``(52.0, None)``; ``"52% in 30m"`` -> ``(52.0, 1800.0)``."""
    match = PROGRESS_RE.match((raw or "").strip())
    if not match:
        raise ValueError("progress looks like `52%` or `52% in 30m`")
    percent = float(match.group("pct"))
    if not 0 <= percent <= 100:
        raise ValueError("percentage has to be between 0 and 100")
    eta = match.group("eta")
    return percent, (parse_duration(eta) if eta else None)


def progress_bar(percent, width=WIDTH):
    """``52`` -> ``█████░░░░░ 52%``, rounded to the nearest block.

    The value is clamped so the bar and the printed number can never disagree.
    """
    value = max(0.0, min(100.0, float(percent)))
    filled = round(value / 100 * width)
    return f"{FILLED * filled}{EMPTY * (width - filled)} {value:g}%"


def looks_like_progress(raw):
    """Whether a field meant to be progress, so a typo is an error, not text."""
    return bool(_PREFIX_RE.match(raw or ""))



def short_duration(seconds):
    """``1800`` -> ``30m``; used in the confirmation line."""
    if seconds >= 3600:
        return f"{seconds / 3600:g}h"
    if seconds >= 60:
        return f"{seconds / 60:g}m"
    return f"{seconds:g}s"


def apply_progress(fields):
    """Turn the first percentage field into a bar.

    Returns ``(fields, percent, eta, problem)``: ``fields`` is a new list with the
    matched field rewritten, ``percent``/``eta`` are ``None`` when no field was a
    percentage, and ``problem`` is a user-facing sentence when a percentage was
    recognised but invalid.
    """
    out = list(fields)
    for index, field in enumerate(out):
        if not field or not looks_like_progress(field):
            continue
        try:
            percent, eta = parse_progress(field)
        except ValueError as exc:
            return out, None, None, str(exc)
        out[index] = progress_bar(percent)
        return out, percent, eta, None
    return out, None, None, None
