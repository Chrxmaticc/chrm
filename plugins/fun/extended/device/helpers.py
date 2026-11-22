"""Client-platform spoof.

The icon Discord draws next to your name (desktop / browser / phone / VR headset /
console) is not something a presence can ask for. It comes from the ``properties``
of the gateway IDENTIFY packet (op 2), sent once per connection, and the server maps
the ``browser`` string onto a platform slot:

    "Discord Client"    -> desktop
    "Discord Android"   -> mobile
    "Discord iOS"       -> mobile
    "Discord VR"        -> vr        (on os Android -- the Quest app's slot)
    "Discord Embedded"  -> embedded  (Xbox / PlayStation)
    anything else       -> web       (what this engine gets by default, because
                                      discord.py-self logs in with Chrome headers)

So ``.device`` writes the choice to the dashboard and drops the connection. The next
login reads it back in ``setup_hook`` and rewrites the ``Headers`` object the
websocket reads for ``op 2``, before the socket opens. It has to be a reconnect:
a RESUME re-uses the session and never repeats the properties.

Slot list, for reference: https://docs.discord.com/developers/events/gateway-events
(the ``client_status`` object has a documented ``vr`` field).
"""
import base64
import json

import aiohttp
from discord.ext import commands

from api_base import BASE_API
_PHONE = {"os": "Android", "browser": "Discord Android", "device": "Discord Android"}
_HEADSET = {"os": "Android", "browser": "Discord VR", "device": "Meta Quest 3"}
_PLAYSTATION = {"os": "Playstation", "browser": "Discord Embedded", "device": "PlayStation 5"}
_DESKTOP = {"os": "Windows", "browser": "Discord Client", "device": "Discord Client"}

#: IDENTIFY properties per device. ``browser`` is the string that picks the slot.
DEVICE_PROPERTIES = {
    "desktop": _DESKTOP,
    "windows": _DESKTOP,
    "macos": {"os": "Mac OS X", "browser": "Discord Client", "device": "Discord Client"},
    "linux": {"os": "Linux", "browser": "Discord Client", "device": "Discord Client"},
    "web": {"os": "Windows", "browser": "Chrome", "device": ""},
    "mobile": _PHONE,
    "android": _PHONE,
    "ios": {"os": "iOS", "browser": "Discord iOS", "device": "iPhone 15"},
    "vr": _HEADSET,
    "quest": _HEADSET,
    "meta": _HEADSET,
    "console": _PLAYSTATION,
    "playstation": _PLAYSTATION,
    "ps5": _PLAYSTATION,
    "xbox": {"os": "Xbox", "browser": "Discord Embedded", "device": "Xbox Series X"},
}

#: Which client_status slot each option lands in -- what Discord will draw.
DEVICE_SLOTS = {
    "desktop": "desktop",
    "windows": "desktop",
    "macos": "desktop",
    "linux": "desktop",
    "web": "web",
    "mobile": "mobile",
    "android": "mobile",
    "ios": "mobile",
    "vr": "VR",
    "quest": "VR",
    "meta": "VR",
    "console": "console",
    "playstation": "console",
    "ps5": "console",
    "xbox": "console",
}


def apply_gateway_platform(client, platform):
    """Make this session identify as ``platform``. Returns True when it did.

    ``Client.login`` builds ``http.headers`` before ``setup_hook`` runs, and
    ``DiscordWebSocket.from_client`` keeps a reference to that very object and reads
    it for ``op 2`` -- so updating ``super_properties`` here is enough. The base64
    blob REST sends is regenerated from the same dict so both halves agree.
    """
    props = DEVICE_PROPERTIES.get((platform or "").strip().lower())
    if not props:
        return False

    headers = getattr(getattr(client, "http", None), "headers", None)
    super_properties = getattr(headers, "super_properties", None)
    if not isinstance(super_properties, dict):
        return False

    super_properties.update(props)
    try:
        headers.encoded_super_properties = base64.b64encode(
            json.dumps(super_properties, separators=(",", ":")).encode()
        ).decode()
    except Exception as e:
        print(f"[DEVICE] could not refresh super properties: {e}")
    return True
