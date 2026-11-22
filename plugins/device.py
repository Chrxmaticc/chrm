"""Device / status-platform spoof.

Two different things are called "device" in Discord, and only one of them is a
client:

* the small desktop/mobile/web icon next to the account. That comes from the
  gateway **IDENTIFY** properties (``os`` / ``browser`` / ``device``), which is why
  this command has always had to reconnect: the properties are read once, at
  handshake time. ``apply_gateway_platform`` rewrites them on the ``Headers`` object
  the websocket reads, before ``op 2`` goes out -- see ``main.py``'s ``setup_hook``.
* the platform icon on an **activity** (phone, controller, VR headset). A user token
  can never be a VR or console *client* -- Discord has no such client -- so ``vr``,
  ``xbox`` and ``playstation`` are drawn there instead, via ``Activity.platform``.
  ``ChrmInstance.change_presence`` stamps it on every presence this engine sends, so
  the badge survives later ``.rpc`` / ``.spotify`` / dashboard changes.
"""
import base64
import json

import aiohttp
import discord
from discord.ext import commands

from api_base import BASE_API

#: IDENTIFY properties per device. Discord maps these onto the client icon.
DEVICE_PROPERTIES = {
    "windows": {"os": "Windows", "browser": "Discord Client", "device": ""},
    "desktop": {"os": "Windows", "browser": "Discord Client", "device": ""},
    "macos": {"os": "Mac OS X", "browser": "Discord Client", "device": ""},
    "linux": {"os": "Linux", "browser": "Discord Client", "device": ""},
    "ios": {"os": "iOS", "browser": "Discord iOS", "device": "iPhone"},
    "android": {"os": "Android", "browser": "Discord Android", "device": "Android"},
    "mobile": {"os": "Android", "browser": "Discord Android", "device": "Android"},
}

#: Platform icon drawn on the activity card.
DEVICE_BADGES = {
    "windows": discord.ActivityPlatform.desktop,
    "desktop": discord.ActivityPlatform.desktop,
    "macos": discord.ActivityPlatform.desktop,
    "linux": discord.ActivityPlatform.desktop,
    "ios": discord.ActivityPlatform.ios,
    "android": discord.ActivityPlatform.android,
    "mobile": discord.ActivityPlatform.android,
    "vr": discord.ActivityPlatform.meta_quest,
    "quest": discord.ActivityPlatform.meta_quest,
    "playstation": discord.ActivityPlatform.ps5,
    "ps5": discord.ActivityPlatform.ps5,
    "xbox": discord.ActivityPlatform.xbox,
}


def device_badge(platform):
    """``ActivityPlatform`` for a saved ``device_platform`` value, or None."""
    return DEVICE_BADGES.get((platform or "").strip().lower())


def apply_gateway_platform(client, platform):
    """Make this session identify as ``platform``. Returns True when anything changed.

    ``Client.login`` builds ``http.headers`` before ``setup_hook`` runs, and
    ``DiscordWebSocket.from_client`` keeps a reference to that very object and reads
    it for ``op 2`` -- so updating ``super_properties`` here is enough, and the
    base64 blob REST sends is regenerated too so both halves agree.
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


class Device(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Use the shared base API URL (see api_base.py)
        self.base_api = BASE_API

    @commands.command()
    async def device(self, ctx, platform: str):
        """spoofs your client device or a status platform. usage: .device mobile / .device vr"""
        platform = platform.strip().lower()
        options = sorted(set(DEVICE_PROPERTIES) | set(DEVICE_BADGES))

        error = self.bot.config.get_emoji("error")
        success = self.bot.config.get_emoji("success")
        loading = self.bot.config.get_emoji("loading")

        if platform not in options:
            return await ctx.send(f"{error} invalid platform. choose from: `{', '.join(options)}`")

        client_spoof = platform in DEVICE_PROPERTIES
        badge = device_badge(platform)

        await ctx.send(f"{loading} switching device to **{platform}**...")

        # 1. Save it first: the engine rereads this before every IDENTIFY, so the
        #    setting has to be on the dashboard before the reconnect below.
        self.bot.config.data.setdefault("settings", {})["device_platform"] = platform
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_api}/api/user/{self.bot.user_id}"
                async with session.patch(url, json={"settings": {"device_platform": platform}}) as resp:
                    if resp.status != 200:
                        print(f"[DEVICE] Failed to save device to DB: {resp.status}")
        except Exception as e:
            print(f"[DEVICE] API error: {e}")

        # 2. Re-send whatever is showing so the badge is live now, not next restart.
        activity = next(iter(self.bot.activities), None)
        if activity is not None and badge is not None:
            try:
                await self.bot.change_presence(activity=activity)
            except Exception as e:
                print(f"[DEVICE] Failed to re-send activity: {e}")

        # 3. VR / consoles have no client session to spoof -- the activity icon is
        #    the whole feature, so do not take the account offline for it.
        if not client_spoof:
            return await ctx.send(
                f"{success} **{platform}** badge is on your status.\n"
                "*discord has no vr/console client for a user account, so this is the "
                "activity icon, not the client tag.*"
            )

        await ctx.send(f"{success} client spoof saved. engine will be back online in ~30 seconds.")
        await self.bot.close()


async def setup(bot):
    await bot.add_cog(Device(bot))
