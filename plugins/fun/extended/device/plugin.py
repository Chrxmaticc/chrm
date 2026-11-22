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
from .helpers import _PHONE, _HEADSET, _PLAYSTATION, _DESKTOP, DEVICE_PROPERTIES, DEVICE_SLOTS, apply_gateway_platform


class DeviceMixin:
    """Commands for this sub-cog; assembled into the package cog."""
    @commands.command()
    async def device(self, ctx, platform: str):
        """spoofs the client icon others see. usage: .device vr / .device mobile"""
        platform = platform.strip().lower()

        error = self.bot.config.get_emoji("error")
        success = self.bot.config.get_emoji("success")
        loading = self.bot.config.get_emoji("loading")

        if platform not in DEVICE_PROPERTIES:
            options = ", ".join(sorted(DEVICE_PROPERTIES))
            return await ctx.send(f"{error} invalid platform. choose from: `{options}`")

        slot = DEVICE_SLOTS[platform]
        await ctx.send(f"{loading} switching device to **{platform}** (`{slot}` icon)...")

        # Save it first: the engine rereads this before every IDENTIFY, so it has to
        # be on the dashboard before the reconnect below.
        self.bot.config.data.setdefault("settings", {})["device_platform"] = platform
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_api}/api/user/{self.bot.user_id}"
                async with session.patch(url, json={"settings": {"device_platform": platform}}) as resp:
                    if resp.status != 200:
                        print(f"[DEVICE] Failed to save device to DB: {resp.status}")
        except Exception as e:
            print(f"[DEVICE] API error: {e}")

        print(f"[DEVICE] {self.bot.user_id} -> {platform}: {DEVICE_PROPERTIES[platform]}")

        await ctx.send(
            f"{success} **{platform}** saved, expect the `{slot}` icon.\n"
            "*reconnecting now -- the new session sends the properties at IDENTIFY, "
            "so the icon shows up in ~30s.*"
        )
        await self.bot.close()
