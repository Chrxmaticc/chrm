"""Libre.fm lookups: Last.fm's API as run by GNU FM.

``https://libre.fm/2.0/`` answers the same ``method`` + ``format=json`` calls as
``ws.audioscrobbler.com/2.0/``. Libre.fm issues no API keys -- the read
methods work with none at all -- so ``.lastfm`` needs nothing configured and
stores no credentials. It is read-only on purpose: scrobbling would need the
account password for ``auth.getMobileSession``, or a token/signature handshake
with nowhere safe to keep it.

Two quirks explain the parsing below:

* the site sits behind Cloudflare and starts answering ``429``/``1015`` HTML
  when it is hit in bursts, so every failure becomes a one-line
  :class:`LastFMError` instead of a traceback in the channel;
* one row arrives as an object and several as a list (``track``,
  ``artist``), so :func:`_rows` normalises both.
"""
import json

import aiohttp

BASE = "https://libre.fm/2.0/"

#: Cloudflare rejects the default aiohttp agent.
UA = "chrm/1.0 (+https://github.com/Chrxmaticc/chrm)"
TIMEOUT = aiohttp.ClientTimeout(total=15)

#: GNU FM takes Last.fm's range names; the aliases are what people type.
PERIODS = {
    "overall": "overall",
    "7day": "7day",
    "1month": "1month",
    "3month": "3month",
    "6month": "6month",
    "12month": "12month",
    "week": "7day",
    "month": "1month",
    "3months": "3month",
    "6months": "6month",
    "year": "12month",
}

PERIOD_LABELS = {
    "overall": "all time",
    "7day": "7 days",
    "1month": "1 month",
    "3month": "3 months",
    "6month": "6 months",
    "12month": "12 months",
}


class LastFMError(Exception):
    """A lookup that failed in a way worth showing to the user."""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def _text(value):
    """``{'#text': 'Artist'}`` -> ``'Artist'``; plain strings pass through."""
    if isinstance(value, dict):
        value = value.get("#text")
    if value is None:
        return ""
    return str(value).strip()


def _rows(value):
    """One row is an object, many are a list."""
    if isinstance(value, dict):
        return [value]
    return list(value or [])


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


async def _call(session, method, **params):
    """GET one API method, or raise :class:`LastFMError` with a readable reason."""
    params.update(method=method, format="json")
    try:
        async with session.get(BASE, params=params, timeout=TIMEOUT) as resp:
            status = resp.status
            body = await resp.text()
    except aiohttp.ClientError as exc:
        raise LastFMError(f"couldn't reach libre.fm ({exc.__class__.__name__})")

    try:
        data = json.loads(body)
    except ValueError:
        if status == 429 or "1015" in body:
            raise LastFMError("libre.fm is rate limiting right now, try again in a minute")
        raise LastFMError(f"libre.fm sent a non-json reply (http {status})")

    if not isinstance(data, dict):
        raise LastFMError(f"libre.fm sent an unexpected reply (http {status})")
    if status != 200:
        raise LastFMError(f"libre.fm returned http {status}")

    error = data.get("error")
    if error:
        if isinstance(error, dict):
            raise LastFMError(_text(error) or "libre.fm rejected the lookup", error.get("code"))
        raise LastFMError(str(error))
    return data


def _track(row):
    stamp = row.get("date") or {}
    attr = row.get("@attr") or {}
    return {
        "name": _text(row.get("name")),
        "artist": _text(row.get("artist")),
        "album": _text(row.get("album")),
        "url": (row.get("url") or "").strip(),
        "now": _text(attr.get("nowplaying")).lower() == "true",
        "played": _int(stamp.get("uts")) or None,
    }


async def recent(session, user, limit=1):
    """Most recent scrobbles, newest first; a currently playing track has ``now``."""
    data = await _call(session, "user.getRecentTracks", user=user, limit=limit)
    return [_track(row) for row in _rows((data.get("recenttracks") or {}).get("track"))]


async def profile(session, user):
    """Account totals. Raises when the user does not exist.

    GNU FM's ``user.getInfo`` only carries ``playcount`` -- there is no
    ``artist_count``/``track_count`` like Last.fm's, so those are not faked.
    """
    data = await _call(session, "user.getInfo", user=user)
    info = data.get("user") or {}
    images = _rows(info.get("image"))
    return {
        "name": _text(info.get("name")) or user,
        "plays": _int(info.get("playcount")),
        "url": (info.get("url") or "").strip() or f"https://libre.fm/user/{user}",
        "image": _text(images[-1].get("#text")) if images else "",
    }


async def top_artists(session, user, period="overall", limit=10):
    """Most played artists over ``period`` (a :data:`PERIODS` value)."""
    data = await _call(session, "user.getTopArtists", user=user, period=period, limit=limit)
    return [
        {
            "name": _text(row.get("name")),
            "plays": _int(row.get("playcount")),
            "url": (row.get("url") or "").strip(),
        }
        for row in _rows((data.get("topartists") or {}).get("artist"))
    ]
