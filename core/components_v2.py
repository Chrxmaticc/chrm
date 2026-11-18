"""Components V2 helpers (Discord's new layout components) + discord.builders share URLs.

A share URL looks like::

    https://discord.builders/embed?v1=1$H4sIAAAAAAAA...

The payload after ``1$`` is plain JSON (the component array Discord expects),
gzipped with mtime=0 and base64 encoded -- nothing exotic:

    base64(gzip(json.dumps(components)))   # gzip level 2-8, mtime 0

Components V2 messages must be sent with the IS_COMPONENTS_V2 flag (1 << 15) and
may not carry ``content``/``embeds``. Two library gotchas, both handled here:

* discord.py-self 2.1.0 models no LayoutView/Container classes and ``.send()`` has
  no ``components``/``flags`` argument, so :func:`send` posts the payload straight
  through the library's HTTP client.
* it also pins the REST base to **API v9** (``INTERNAL_API_VERSION = 9``). V2
  components do not exist on v9, so these requests go to v10.

**User accounts cannot send Components V2 at all.** With a self-bot token the API
answers ``50006 Cannot send an empty message`` on v9 and v10 alike, because the v2
flag is only honoured for applications. So the practical use of this module is
:func:`share_url` -- encode the layout and post the discord.builders link.
:func:`send` is kept for when a real bot token is available.
"""
import base64
import gzip
import json
from typing import Any, Dict, Iterable, List, Optional

from discord.http import Route

#: Components V2 only exists on API v10+.
API_VERSION = 10


class _ComponentsV2Route(Route):
    """Same route, but against a REST version that understands layout components."""

    BASE = f"https://discord.com/api/v{API_VERSION}"

#: IS_COMPONENTS_V2 -- required for layout components.
V2_FLAG = 1 << 15

SHARE_PREFIX = "https://discord.builders/embed?v1="
PAYLOAD_PREFIX = "1$"

# Layout component types.
ACTION_ROW = 1
BUTTON = 2
SECTION = 9
TEXT_DISPLAY = 10
THUMBNAIL = 11
MEDIA_GALLERY = 12
SEPARATOR = 14
CONTAINER = 17


# ---------------------------------------------------------------- builders
def text(content: str) -> Dict[str, Any]:
    """Type 10 -- markdown text block (max 4000 chars)."""
    return {"type": TEXT_DISPLAY, "content": content}


def separator(divider: bool = True, spacing: int = 1) -> Dict[str, Any]:
    """Type 14 -- thin divider; spacing: 1 = small, 2 = large."""
    return {"type": SEPARATOR, "divider": divider, "spacing": spacing}


def section(content: str, accessory: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Type 9 -- text with an optional thumbnail/button on the right."""
    payload: Dict[str, Any] = {"type": SECTION, "components": [text(content)]}
    if accessory:
        payload["accessory"] = accessory
    return payload


def container(
    *children: Dict[str, Any],
    accent_color: Optional[int] = None,
    spoiler: bool = False,
) -> Dict[str, Any]:
    """Type 17 -- the coloured box that wraps everything (max 10 children)."""
    return {
        "type": CONTAINER,
        "accent_color": accent_color,
        "spoiler": spoiler,
        "components": [c for c in children if c],
    }


# ---------------------------------------------------------------- share urls
def encode_url_payload(components: List[Dict[str, Any]]) -> str:
    """The part after ``?v1=`` -- ``1$`` + base64(gzip(json))."""
    raw = json.dumps(components, separators=(",", ":"), ensure_ascii=False).encode()
    # Level 8 + mtime=0 reproduces discord.builders' own bytes exactly.
    packed = gzip.compress(raw, compresslevel=8, mtime=0)
    return PAYLOAD_PREFIX + base64.b64encode(packed).decode()


def share_url(components: List[Dict[str, Any]]) -> str:
    """A discord.builders link that renders ``components`` the same way."""
    return SHARE_PREFIX + encode_url_payload(components)


#: The tag discord.builders serves and Discord's unfurler reads.
EMBED_SCRIPT_ID = "discord:component-embed"


def build_embed_page(components: List[Dict[str, Any]]) -> str:
    """The HTML that makes Discord unfurl a component card.

    discord.builders serves exactly this: one component wrapped in
    ``{"component": ...}`` inside a ``<script id="discord:component-embed">``.
    Useful for self-hosting a short share page on the engine's own web server.
    """
    component = components[0] if isinstance(components, list) else components
    payload = json.dumps({"component": component}, separators=(",", ":"), ensure_ascii=False)
    # Guard against a content string closing the script tag early.
    payload = payload.replace("</", "<\\/")
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        f'<script id="{EMBED_SCRIPT_ID}" type="application/json">{payload}</script>'
        "</head><body>component embed</body></html>"
    )


def decode_share_url(url_or_payload: str) -> List[Dict[str, Any]]:
    """Reverse of :func:`share_url`; handy for checking what a link contains."""
    value = url_or_payload.split("v1=", 1)[-1]
    if value.startswith(PAYLOAD_PREFIX):
        value = value[len(PAYLOAD_PREFIX):]
    return json.loads(gzip.decompress(base64.b64decode(value)))


# ---------------------------------------------------------------- sending
def build_message(components: List[Dict[str, Any]], **extra: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"components": components, "flags": V2_FLAG}
    payload.update(extra)
    return payload


async def send(channel, components: Iterable[Dict[str, Any]], *, bot=None, **extra: Any):
    """Post a Components V2 message to ``channel`` (a channel object or an id).

    Requires a **bot** token -- user accounts/self-bots always get a 50006.
    """
    channel_id = getattr(channel, "id", channel)
    http = (bot or getattr(channel, "_state", None)).http
    route = _ComponentsV2Route("POST", "/channels/{channel_id}/messages", channel_id=channel_id)
    payload = build_message(list(components), **extra)
    try:
        return await http.request(route, json=payload)
    except Exception as exc:
        # A 50006 here means the payload arrived empty, i.e. the components were
        # rejected/dropped -- worth seeing exactly what was posted and where.
        print(f"[components_v2] {route.method} {route.url} failed: {exc!r}")
        print(f"[components_v2] payload: {json.dumps(payload)[:600]}")
        raise


def count_components(components: Iterable[Dict[str, Any]]) -> int:
    """Discord v2 messages allow at most 40 components, nested ones included."""
    total = 0
    for component in components:
        total += 1
        for key in ("components",):
            children = component.get(key) or []
            if children:
                total += count_components(children)
    return total
