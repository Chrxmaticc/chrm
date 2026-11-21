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

class RPC(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.custom_rotator_task = None

    def cog_unload(self):
        if self.custom_rotator_task and not self.custom_rotator_task.done():
            self.custom_rotator_task.cancel()

    # ==========================================
    # 1. SEND THE MENU (WITH BUTTONS)
    # ==========================================
    @commands.command()
    async def rpcmenu(self, ctx):
        """opens the interactive rpc manager using raw components"""
        payload = {
            "content": "### RPC Manager\nSelect an activity type below to set your Rich Presence.",
            "components": [
                {
                    "type": 1,  # Action Row
                    "components": [
                        {"type": 2, "style": 1, "label": "Playing", "custom_id": "rpc_btn_playing", "emoji": {"name": "🎮"}},
                        {"type": 2, "style": 1, "label": "Listening", "custom_id": "rpc_btn_listening", "emoji": {"name": "🎧"}},
                        {"type": 2, "style": 1, "label": "Watching", "custom_id": "rpc_btn_watching", "emoji": {"name": "📺"}}
                    ]
                },
                {
                    "type": 1,  # Action Row
                    "components": [
                        {"type": 2, "style": 4, "label": "Clear Status", "custom_id": "rpc_btn_clear", "emoji": {"name": "🛑"}}
                    ]
                }
            ]
        }

        url = f"https://discord.com/api/v9/channels/{ctx.channel.id}/messages"
        headers = {
            "Authorization": self.bot.http.token,
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status not in (200, 201):
                        error_text = await resp.text()
                        await ctx.send(f"❌ Failed to send menu: {resp.status} - {error_text}")
        except Exception as e:
            await ctx.send(f"❌ Error sending menu: {e}")

    # ==========================================
    # 2. RAW INTERACTION HANDLER (CATCHES BUTTONS & MODALS)
    # ==========================================
    @commands.Cog.listener()
    async def on_socket_response(self, msg):
        if msg.get("t") != "INTERACTION_CREATE":
            return

        data = msg.get("d", {})
        interaction_type = data.get("type")
        custom_id = data.get("data", {}).get("custom_id", "")
        interaction_id = data.get("id")
        interaction_token = data.get("token")

        # Only handle our RPC interactions
        if not custom_id or not custom_id.startswith("rpc_"):
            return

        url = f"https://discord.com/api/v9/interactions/{interaction_id}/{interaction_token}/callback"
        headers = {
            "Authorization": self.bot.http.token,
            "Content-Type": "application/json",
        }

        # --- BUTTON CLICKS (Type 3) ---
        if interaction_type == 3:
            if custom_id in ["rpc_btn_playing", "rpc_btn_listening", "rpc_btn_watching"]:
                act_type = custom_id.split("_")[-1]
                
                # Send a Modal (Type 9)
                modal_payload = {
                    "type": 9,
                    "data": {
                        "title": f"Set {act_type.title()} Status",
                        "custom_id": f"rpc_modal_submit_{act_type}",
                        "components": [
                            {"type": 1, "components": [{"type": 4, "custom_id": "rpc_name", "label": "App/Game Name", "style": 1, "placeholder": "e.g. Minecraft", "required": True}]},
                            {"type": 1, "components": [{"type": 4, "custom_id": "rpc_details", "label": "Details (Line 1)", "style": 1, "required": False}]},
                            {"type": 1, "components": [{"type": 4, "custom_id": "rpc_state", "label": "State (Line 2)", "style": 1, "required": False}]},
                            {"type": 1, "components": [{"type": 4, "custom_id": "rpc_image", "label": "Discord CDN Image URL", "style": 1, "placeholder": "https://cdn.discordapp.com/...", "required": False}]}
                        ]
                    }
                }
                async with aiohttp.ClientSession() as session:
                    await session.post(url, json=modal_payload, headers=headers)
                return

            elif custom_id == "rpc_btn_clear":
                self.bot.locked_presence = False
                await self.bot.change_presence(activity=None)
                response = {"type": 4, "data": {"content": "🛑 RPC forcefully cleared.", "flags": 64}}
                async with aiohttp.ClientSession() as session:
                    await session.post(url, json=response, headers=headers)
                return

        # --- MODAL SUBMITS (Type 5) ---
        if interaction_type == 5 and custom_id.startswith("rpc_modal_submit_"):
            act_type_str = custom_id.replace("rpc_modal_submit_", "")
            components = data.get("data", {}).get("components", [])
            name, details, state, image_url = None, None, None, None

            for row in components:
                for comp in row.get("components", []):
                    cid = comp.get("custom_id")
                    val = comp.get("value")
                    if cid == "rpc_name": name = val
                    elif cid == "rpc_details": details = val
                    elif cid == "rpc_state": state = val
                    elif cid == "rpc_image": image_url = val

            types = {"playing": discord.ActivityType.playing, "listening": discord.ActivityType.listening, "watching": discord.ActivityType.watching}
            assets = {}
            if image_url:
                assets["large_image"] = format_image_url(image_url)
                if details: assets["large_text"] = details

            try:
                self.bot.locked_presence = True
                await self.bot.change_presence(activity=discord.Activity(
                    type=types[act_type_str], name=name, details=details, state=state,
                    assets=assets if assets else None
                ))
                response = {"type": 4, "data": {"content": f"✅ RPC updated to **{act_type_str.title()} {name}**.", "flags": 64}}
            except Exception as e:
                response = {"type": 4, "data": {"content": f"❌ Failed to set RPC: {e}", "flags": 64}}

            async with aiohttp.ClientSession() as session:
                await session.post(url, json=response, headers=headers)
            return

    # ==========================================
    # 3. TEXT COMMANDS
    # ==========================================
    @commands.command()
    async def rpc(self, ctx, activity_type: str, *, args):
        """rich presence, with icons and an optional progress bar.

        usage: .rpc playing name | details | state | image | duration=3:45 | small=<icon url>
        """
        activity_type = activity_type.lower()

        # Positional fields keep their old order; key=value tokens can sit anywhere.
        parts, options = [], {}
        for chunk in (p.strip() for p in args.split("|")):
            key, sep, value = chunk.partition("=")
            key = key.strip().lower()
            if sep and key in ("duration", "small", "icon", "elapsed"):
                options[key] = value.strip()
            elif chunk.lower() == "elapsed":
                options["elapsed"] = "1"
            else:
                parts.append(chunk)

        name = parts[0] if parts and parts[0] else "chrm"
        details = parts[1] if len(parts) > 1 and parts[1] else None
        state = parts[2] if len(parts) > 2 and parts[2] else None
        large_img = parts[3] if len(parts) > 3 and parts[3] else None

        types = {"playing": discord.ActivityType.playing, "watching": discord.ActivityType.watching, "listening": discord.ActivityType.listening, "competing": discord.ActivityType.competing}
        if activity_type not in types:
            return await ctx.send(f"{self.bot.config.get_emoji('error')} invalid type.")

        # Start *and* end is what draws the bar; start alone only counts up. Datetimes,
        # because discord.py converts them to the milliseconds the gateway expects.
        seconds = parse_duration(options.get("duration"))
        start = end = None
        if seconds:
            start = discord.utils.utcnow()
            end = start + timedelta(seconds=seconds)
        elif options.get("elapsed"):
            start = discord.utils.utcnow()
        timestamps = discord.ActivityTimestamps(start=start, end=end) if (start or end) else None

        large = format_image_url(large_img) if large_img else None
        small = format_image_url(options.get("small") or options.get("icon")) or None

        # A bare URL is stored verbatim and draws nothing, so trade it for an mp: key first.
        raw = [url for url in (large, small) if needs_proxy(url)]
        app_id = (options.get("app") or os.getenv("RPC_APPLICATION_ID") or "").strip()
        if raw:
            if not app_id.isdigit():
                return await ctx.send(
                    "icons need one more piece: Discord won't render a raw image URL. "
                    "Add `RPC_APPLICATION_ID=<app id>` to `.env` (create any application at "
                    "discord.com/developers/applications -> New Application, copy the Application ID) "
                    "or pass `app=<app id>` in the command. Discord CDN links and `spotify:<hash>` "
                    "already work without it."
                )
            try:
                proxied = await self.bot.proxy_external_application_assets(int(app_id), *raw)
            except Exception as e:
                return await ctx.send(f"{self.bot.config.get_emoji('error')} media proxy failed: `{e}`")
            resolved = dict(zip(raw, proxied))
            large, small = resolved.get(large, large), resolved.get(small, small)

        assets = None
        if large or small:
            # ActivityAssets, not a dict: its constructor rewrites CDN links into mp:
            assets = discord.ActivityAssets(
                large_image=large, large_text=details if large else None,
                small_image=small, small_text=name if small else None,
            )

        try:
            self.bot.locked_presence = True
            await self.bot.change_presence(activity=discord.Activity(
                type=types[activity_type], name=name, details=details, state=state,
                assets=assets, timestamps=timestamps,
                application_id=int(app_id) if (raw and app_id.isdigit()) else None,
            ))
            note = ""
            if seconds:
                note = f" · bar over {options.get('duration')}"
            elif start:
                note = " · counting up"
            await ctx.send(f"{self.bot.config.get_emoji('success')} rpc updated: {activity_type} **{name}**{note}")
        except Exception as e:
            await ctx.send(f"{self.bot.config.get_emoji('error')} error: {e}")

    @commands.command(name="presencedump", aliases=["pd"])
    async def presencedump(self, ctx):
        """prints the exact presence payload we send, plus bar/art checks (diagnostic)"""
        activities = list(self.bot.activities)
        if not activities:
            return await ctx.send("no activity set right now. run `.spotify ...` or `.rpc ...` first.")

        urls = []
        for activity in activities:
            for value in (activity.to_dict().get("assets") or {}).values():
                if isinstance(value, str) and value.startswith(("http://", "https://")) and value not in urls:
                    urls.append(value)

        extras = []
        if urls:
            async with aiohttp.ClientSession(headers={"User-Agent": "chrm/1.0"}) as session:
                checks = await asyncio.gather(*(_probe(session, url) for url in urls))
            extras = ["", "**asset reachability**"] + list(checks)

        for chunk in _chunks(presence_report(activities, extras)):
            await ctx.send(chunk)

    @commands.command()
    async def stream(self, ctx, url: str, *, title):
        """usage: .stream https://twitch.tv/you title here"""
        if not url.startswith("http"):
            return await ctx.send(f"{self.bot.config.get_emoji('error')} invalid url.")
        self.bot.locked_presence = True
        await self.bot.change_presence(activity=discord.Streaming(name=title, url=url))
        await ctx.send(f"{self.bot.config.get_emoji('success')} now streaming: **{title}**")

    @commands.command()
    async def customstatus(self, ctx, *, text):
        """sets a custom text status"""
        self.bot.locked_presence = True
        await self.bot.change_presence(activity=discord.CustomActivity(name=text))
        await ctx.send(f"{self.bot.config.get_emoji('success')} custom status set to: {text}")

    @commands.command()
    async def clearstatus(self, ctx):
        """wipes the active rpc"""
        self.bot.locked_presence = False
        await self.bot.change_presence(activity=None)
        await ctx.send(f"{self.bot.config.get_emoji('success')} presence completely wiped.")

    # ==========================================
    # 4. STATUS ROTATOR
    # ==========================================
    @commands.command()
    async def startrotator(self, ctx, *, args):
        """usage: .startrotator status1, status2 | 5m"""
        match = re.search(r'\|\s*(\d+)([smh])$', args)
        if not match: return await ctx.send("missing time. usage: `.startrotator status1, status2 | 5m`")
        amount, unit = int(match.group(1)), match.group(2)
        total_seconds = amount * {'s': 1, 'm': 60, 'h': 3600}[unit]
        statuses = [s.strip() for s in args[:match.start()].strip().split(",") if s.strip()]
        if not statuses: return await ctx.send("no statuses provided.")
        if self.custom_rotator_task and not self.custom_rotator_task.done(): self.custom_rotator_task.cancel()
        
        self.bot.locked_presence = True
        self.custom_rotator_task = asyncio.create_task(self._run_custom_rotator(statuses, total_seconds))
        await ctx.send(f"{self.bot.config.get_emoji('success')} rotator started.")

    async def _run_custom_rotator(self, statuses, interval):
        try:
            index = 0
            while True:
                await self.bot.change_presence(activity=discord.CustomActivity(name=statuses[index % len(statuses)]))
                index += 1
                await asyncio.sleep(interval)
        except asyncio.CancelledError: pass

    @commands.command()
    async def stoprotator(self, ctx):
        if self.custom_rotator_task and not self.custom_rotator_task.done():
            self.custom_rotator_task.cancel()
            self.bot.locked_presence = False
            await self.bot.change_presence(activity=None)
            await ctx.send(f"{self.bot.config.get_emoji('success')} rotator stopped.")

async def setup(bot):
    await bot.add_cog(RPC(bot))
