import discord
from discord.ext import commands
import asyncio
import os
import re
from datetime import timedelta
import json
import aiohttp
SPOTIFY_IMAGE_RE = re.compile(
    r"https?://(?:i\.scdn\.co|image-cdn[-\w.]*\.spotifycdn\.com)/image/([A-Za-z0-9]+)"
)
DURATION_RE = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})$")


def parse_duration(text):
    """'3:45' or '1:02:03' -> seconds, or None."""
    match = DURATION_RE.match((text or "").strip())
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)


ASSET_PREFIX_RE = re.compile(r"^(?:mp|spotify|twitch|youtube):")


def needs_proxy(url):
    """True when a URL would land in the payload unresolved, i.e. render as a blank icon.

    Clients only draw asset keys they can resolve: ``mp:``/``spotify:``/``twitch:``/
    ``youtube:`` prefixed ids, Discord CDN links (which the library rewrites to ``mp:``),
    or an application asset id. A bare ``https://`` URL is not one of those, so it has to
    be traded for a media-proxy key first -- see ``RPC_APPLICATION_ID``.
    """
    if not url or not url.startswith(("http://", "https://")) or ASSET_PREFIX_RE.match(url):
        return False
    patterns = (
        discord.ActivityAssets.MP_REGEX,
        discord.ActivityAssets.TWITCH_REGEX,
        discord.ActivityAssets.YOUTUBE_REGEX,
        discord.ActivityAssets.SPOTIFY_REGEX,
    )
    return not any(pattern.match(url) for pattern in patterns)


def format_image_url(url):
    """Normalise a pasted image reference into the form the payload wants.

    * ``mp:`` / ``spotify:`` / ``twitch:`` / ``youtube:`` URIs pass through.
    * Spotify CDN links become ``spotify:<hash>`` -- the only form Spotify's CDN
      resolves.
    * Discord CDN / media-proxy links are left alone; ``ActivityAssets`` turns them
      into ``mp:`` when the activity is built.
    * Anything else stays a URL and must go through ``needs_proxy``/the media proxy,
      because a raw URL is stored verbatim and the client has nothing to resolve.
    """
    if not url:
        return None
    url = str(url).strip()
    if url.startswith(("mp:", "spotify:", "twitch:", "youtube:")):
        return url

    match = SPOTIFY_IMAGE_RE.match(url)
    if match:
        return f"spotify:{match.group(1)}"
    return url


def _chunks(text, limit=1900):
    """Split long diagnostics under Discord's 2000-char message cap."""
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        yield text[:cut]
        text = text[cut:].lstrip("\n")
    if text:
        yield text


async def _probe(session, url):
    """One-line liveness check: icons render only for a directly fetchable image."""
    timeout = aiohttp.ClientTimeout(total=5)
    try:
        async with session.head(url, timeout=timeout, allow_redirects=False) as resp:
            status, kind = resp.status, resp.headers.get("content-type", "?")
        if status in (403, 405):  # host dislikes HEAD; try a real GET but do not read it
            async with session.get(url, timeout=timeout, allow_redirects=False) as resp:
                status, kind = resp.status, resp.headers.get("content-type", "?")
    except Exception as e:
        return f"`{url}` — unreachable ({e.__class__.__name__})"

    if status in (301, 302, 303, 307, 308):
        return f"`{url}` — {status} redirect, Discord will fetch the redirect target (may be a web page, not an image)"
    if status != 200:
        return f"`{url}` — {status}, Discord cannot proxy it"
    if not kind.startswith("image/"):
        return f"`{url}` — 200 but `{kind}`, not an image"
    return f"`{url}` — 200 `{kind}`, fetchable"


def presence_report(activities, extras=()):
    """Readable checks for the live activity payloads we sent.

    Anything the client needs in order to draw a progress bar or an album cover
    has to be in this dict: flags 48, sync_id, start+end timestamps, and the
    ``spotify:<hash>`` / resolvable asset id.
    """
    lines = []
    for activity in activities:
        data = activity.to_dict()
        lines.append(f"**{data.get('name')}** · type {data.get('type')}")

        flags = data.get("flags") or 0
        if isinstance(activity, discord.Spotify):
            state = "ok (sync|play)" if flags & 48 == 48 else "MISSING sync|play -> no bar"
            lines.append(f"flags `{flags}` — {state}")
            sync_id = data.get("sync_id")
            if not sync_id:
                lines.append("sync_id missing -> no Listen Along")
            else:
                shape = "ok" if len(sync_id) == 22 else "unexpected length -> no Listen Along"
                lines.append(f"sync_id `{sync_id}` — {shape}")

        timestamps = data.get("timestamps") or {}
        start, end = timestamps.get("start"), timestamps.get("end")
        if start and end:
            lines.append(f"timestamps `{start}` -> `{end}` ({(end - start) / 1000:.1f}s) — ok, draws the bar")
        elif start:
            lines.append(f"timestamps start only (`{start}`) — counts up, no bar")
        else:
            lines.append("timestamps missing — no bar")

        assets = data.get("assets") or {}
        for key in ("large_image", "small_image"):
            value = assets.get(key)
            if not value:
                continue
            if value.startswith("spotify:"):
                verdict = "ok, Spotify art"
            elif value.startswith("mp:"):
                verdict = "mp: proxied asset — renders"
            elif value.startswith(("twitch:", "youtube:")):
                verdict = "ok"
            elif value.startswith(("http://", "https://")):
                verdict = "raw url — NOT rendered, needs the media proxy (app id)"
            else:
                verdict = "application asset id"
            lines.append(f"{key} `{value}` — {verdict}")

        if data.get("party"):
            lines.append(f"party `{data['party']}`")
        if data.get("application_id"):
            lines.append(f"application_id `{data['application_id']}`")

    lines.extend(extras)
    payload = [activity.to_dict() for activity in activities]
    return "\n".join(lines) + "\n```json\n" + json.dumps(payload, indent=1) + "\n```"
