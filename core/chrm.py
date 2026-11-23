"""The engine: one ChrmInstance per dashboard user, plus the sync loop that keeps them alive.

``main.py`` is only a runner -- it loads ``.env`` and calls :func:`main` here. Everything
that used to live at the top of ``main.py`` is in this module, grouped the same way:

    1. web server for Render
    2. ChrmInstance (one logged-in self-bot)
    3. engine setup + sync loop
    4. runner
"""
import os
import asyncio
import random
import time
import gc
import psutil
from dotenv import load_dotenv
from api_base import BASE_API
from core import api, prefs  # shared aiohttp session + dashboard writes
from core.client.loader import FRAMEWORK_EXTENSIONS, iter_extensions
from core.config import Config
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import discord
from discord.ext import commands
from datetime import datetime, timezone

# Load .env before anything reads os.environ (PORT, API_URL, ENGINE_SECRET).
load_dotenv()


def _timestamp(value):
    """Dashboard timestamps arrive in seconds or milliseconds; return an aware datetime."""
    if not value:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if value < 1e11:  # seconds, not milliseconds
        value *= 1000
    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None

# ==========================================
# 1. WEB SERVER FOR RENDER
# ==========================================
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"chrm engine online")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()

    def log_message(self, format, *args):
        pass

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    print(f"🌐 [SERVER] Web server running on port {port}")
    server.serve_forever()

def start_web_server():
    """Render needs *something* listening on $PORT; started from :func:`main`."""
    threading.Thread(target=run_web_server, daemon=True).start()

# ==========================================
# 2. CONFIG
# ==========================================
# Defaults and the per-instance wrapper both live in core/config.py so that any
# module can read EMOJIS.DENY without a bot instance.

# ==========================================
# 3. MULTI-USER BOT INSTANCE
# ==========================================
class ChrmInstance(commands.Bot):
    def __init__(self, user_id, token, user_config_data):
        self.config = Config(user_config_data)

        super().__init__(command_prefix=self.config.get_prefixes(), self_bot=True, help_command=None)

        self.user_id = user_id
        self.token = token
        self.locked_presence = False
        self._ready_once = False
        #: extension -> why it failed to load, shown by .sysinfo
        self.load_errors = {}

    async def human_delay(self):
        settings = self.config.data.get("settings", {})
        if settings.get("delays_enabled", True):
            min_d = settings.get("delay_min", 1.5)
            max_d = settings.get("delay_max", 4.5)
            await asyncio.sleep(random.uniform(min_d, max_d))

    async def invoke(self, ctx):
        command = getattr(ctx, "command", None)
        names = {getattr(command, "name", "")}
        parent = getattr(command, "parent", None)
        if parent is not None:
            names.add(getattr(parent, "name", ""))
        names.discard("")

        # .disable / .cooldown are enforced here because every command passes
        # through invoke, and a blocked command must answer instead of vanishing.
        blocked = next((name for name in names if not prefs.is_allowed(self, name)), None)
        if blocked:
            error = self.config.get_emoji("error")
            return await ctx.send(f"{error} `{blocked}` is disabled. `.enable {blocked}`")

        try:
            wait = prefs.cooldown_left(self)
        except Exception:  # noqa: BLE001 - a broken pref must not break commands
            wait = 0.0
        if wait > 0 and not any(name in prefs.BYPASS for name in names):
            error = self.config.get_emoji("error")
            return await ctx.send(f"{error} slow down — **{wait:.1f}s** left.")
        prefs.mark(self)

        await self.human_delay()
        await super().invoke(ctx)

    async def setup_hook(self):
        # The device icon is decided by the IDENTIFY properties, and login() has
        # already built http.headers by now: the websocket reads that same object
        # for op 2, so this has to land before the socket connects.
        from plugins.fun.extended.device.helpers import apply_gateway_platform

        platform = self.config.data.get("settings", {}).get("device_platform")
        if platform and apply_gateway_platform(self, platform):
            print(f"[DEVICE] {self.user_id} identifying as {platform}")

        # Framework cogs first (help renders the plugin surface), then every
        # plugins/<cog>/ package that has a plugin.py.
        for extension in (*FRAMEWORK_EXTENSIONS, *iter_extensions()):
            try:
                await self.load_extension(extension)
            except Exception as e:
                # A package that fails to import takes every command in it with it,
                # and a missing command is answered with silence (CommandNotFound is
                # ignored), so the reason has to survive somewhere visible: .sysinfo.
                failure = f"{type(e).__name__}: {e}"
                self.load_errors[extension] = failure
                print(f"[PLUGIN ERROR] Failed to load {extension} for {self.user_id}: {failure}")

    async def on_ready(self):
        print(f"✅ [ONLINE] logged in as {self.user.name} (id: {self.user_id})")

        # on_ready fires on every reconnect. Re-applying the dashboard RPC there would
        # overwrite a presence the user set by hand (.rpc, .spotify, .customstatus...),
        # so only the first ready (or a free presence slot) takes the dashboard's version.
        first_ready = not self._ready_once
        self._ready_once = True
        if first_ready or not self.locked_presence:
            await self.apply_dashboard_rpc(self.config.data.get("settings", {}))

    async def _dashboard_assets(self, url, large_text=None):
        """Turn a dashboard icon into (drawable assets, app id it was minted under).

        A raw URL in the payload draws nothing, so it has to become an ``mp:`` key
        first: ``ActivityAssets`` handles CDN links, and any other host needs
        ``RPC_APPLICATION_ID`` so Discord's media proxy will mint one.
        """
        from plugins.fun.extended.rpc.helpers import format_image_url

        value = format_image_url(url)
        if not value:
            return None, None

        app_id = None
        if value.startswith(("http://", "https://")):
            raw = (os.getenv("RPC_APPLICATION_ID") or "").strip()
            if raw.isdigit():
                try:
                    value = (await self.proxy_external_application_assets(int(raw), value))[0]
                    app_id = int(raw)
                except Exception as e:
                    print(f"[RPC] media proxy failed for {self.user_id}: {e}")

        return discord.ActivityAssets(large_image=value, large_text=large_text), app_id

    async def apply_dashboard_rpc(self, settings):
        rpc_data = settings.get("rpc")
        if rpc_data and rpc_data.get("name"):
            try:
                # --- SPOTIFY: sync_id + flags 48 + start/end is what draws the bar ---
                if rpc_data.get("type") == "listening" and rpc_data.get("name") == "Spotify":
                    assets, _ = await self._dashboard_assets(
                        rpc_data.get("album_image") or rpc_data.get("image_url")
                    )
                    track_id = str(rpc_data.get("track_id") or rpc_data.get("sync_id") or "").replace("spotify:track:", "")
                    self.locked_presence = True
                    await self.change_presence(activity=discord.Activity(
                        type=discord.ActivityType.listening,
                        name="Spotify",
                        details=rpc_data.get("details"),
                        state=rpc_data.get("state"),
                        sync_id=track_id or None,
                        application_id=409155198293508107,
                        flags=discord.ActivityFlags(sync=True, play=True) if track_id else None,
                        assets=assets,
                        timestamps=discord.ActivityTimestamps(
                            start=_timestamp(rpc_data.get("start_time")),
                            end=_timestamp(rpc_data.get("end_time")),
                        ) or None,
                    ))
                    print(f"[RPC] Applied Spotify spoof for {self.user_id}")
                    return

                # --- STANDARD RPC LOGIC ---
                types = {
                    "playing": discord.ActivityType.playing,
                    "watching": discord.ActivityType.watching,
                    "listening": discord.ActivityType.listening,
                    "competing": discord.ActivityType.competing
                }
                
                assets, asset_app_id = await self._dashboard_assets(
                    rpc_data.get("image_url"), rpc_data.get("details")
                )

                timestamps = None
                if rpc_data.get("elapsed"):
                    timestamps = discord.ActivityTimestamps(start=datetime.now(timezone.utc))

                self.locked_presence = True
                await self.change_presence(activity=discord.Activity(
                    type=types.get(rpc_data["type"], discord.ActivityType.playing),
                    name=rpc_data["name"],
                    details=rpc_data.get("details"),
                    state=rpc_data.get("state"),
                    assets=assets,
                    application_id=asset_app_id,
                    timestamps=timestamps
                ))
            except Exception as e:
                print(f"[RPC ERROR] Failed to apply RPC for {self.user_id}: {e}")

    async def on_command_error(self, ctx, error):
        if isinstance(error, (commands.CommandNotFound, commands.CheckFailure)):
            return
        if isinstance(error, commands.CommandOnCooldown):
            return await ctx.send(f"slow down. try again in {error.retry_after:.1f}s.")
        
        error_emoji = self.config.get_emoji("error")
        await ctx.send(f"{error_emoji} error: {str(error).lower()}")

# ==========================================
# 4. ENGINE SETUP & SYNC LOOP
# ==========================================
API_URL = os.environ.get("API_URL")
ENGINE_SECRET = os.environ.get("ENGINE_SECRET")

if API_URL:
    _base = API_URL.rstrip("/")
    BOTS_URL = _base if _base.endswith("/api/engine/bots") else f"{_base}/api/engine/bots"
else:
    BOTS_URL = None

running_bots = {}
login_cooldowns = {} 
_auth_warned_at = {}

async def fetch_users_from_api():
    if not BOTS_URL or not ENGINE_SECRET:
        return None
        
    headers = {"x-engine-secret": ENGINE_SECRET}
    
    try:
        # One shared session for the whole engine (see core/api.py).
        async with api.session().get(BOTS_URL, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            if resp.status in (401, 403):
                if time.time() - _auth_warned_at.get("t", 0) > 60:
                    _auth_warned_at["t"] = time.time()
                    print(f"🔑 [API AUTH] {BOTS_URL} rejected ENGINE_SECRET ({resp.status}).")
            return None 
    except Exception as e:
        print(f"🌐 [API ERROR] {BOTS_URL}: {type(e).__name__}: {e}")
        return None

async def start_bot_for_user(user_data):
    token = user_data.get("token")
    uid = user_data["discord_id"]
    
    if not token:
        return

    print(f"⏳ [LOGIN] Connecting for {uid}...")
    bot = ChrmInstance(uid, token, user_data)
    running_bots[uid] = bot

    try:
        await bot.start(token)
    except discord.LoginFailure:
        print(f"❌ [LOGIN FAILED] Invalid token for {uid}. Cooldown 5m.")
        login_cooldowns[uid] = time.time() + 300 
    except Exception as e:
        print(f"❌ [LOGIN CRASHED] {uid}: {e}")
        login_cooldowns[uid] = time.time() + 300
    finally:
        if uid in running_bots:
            del running_bots[uid]
            print(f"🧹 [CLEANUP] Removed instance for {uid}")

async def sync_loop():
    print("🤖 [SYNC] Starting memory-safe sync loop...")
    api_errors = 0
    
    while True:
        start_time = time.time()
        
        # MEMORY WATCHDOG
        process = psutil.Process(os.getpid())
        ram_usage = process.memory_info().rss / 1024 / 1024 # In MB
        
        if ram_usage > 460: 
            print(f"🚨 [CRITICAL] RAM USAGE AT {ram_usage:.1f}MB. Skipping sync to prevent crash.")
            gc.collect() 
            await asyncio.sleep(15)
            continue
        
        users = await fetch_users_from_api()
        
        if users is None:
            api_errors += 1
            if api_errors % 5 == 1: 
                print("⚠️ [API WARNING] API connection failed. Backing off...")
            await asyncio.sleep(10)
            continue
        
        api_errors = 0 

        # Clean up ghost instances
        for uid in list(running_bots.keys()):
            if running_bots[uid].is_closed():
                del running_bots[uid]
                print(f"🧹 [CLEANUP] Detected closed instance for {uid}. Removed.")
        
        gc.collect()

        for user in users:
            uid = user["discord_id"]
            is_active = user["is_active"]
            settings = user["settings"]

            if not is_active:
                if uid in running_bots:
                    print(f"🛑 [STOP] Disconnecting bot for {uid}")
                    await running_bots[uid].close()
                continue

            if uid in login_cooldowns:
                if time.time() < login_cooldowns[uid]:
                    continue 
                else:
                    del login_cooldowns[uid] 

            if is_active and uid not in running_bots:
                if ram_usage > 420:
                    print(f"⚠️ [RAM LIMIT] Refusing to start {uid}. Not enough memory.")
                    continue
                    
                print(f"🚀 [START] User {uid} is active. Launching...")
                asyncio.create_task(start_bot_for_user(user))
                continue

            if is_active and uid in running_bots:
                bot = running_bots[uid]
                # update_from_dashboard returns True only when the blob actually
                # changed, so this no longer re-applies every 3 seconds.
                if bot.config.update_from_dashboard(user):
                    bot.command_prefix = bot.config.get_prefixes()
                    await bot.apply_dashboard_rpc(user.get("settings", {}))

        elapsed = time.time() - start_time
        sleep_time = max(0, 3.0 - elapsed)
        await asyncio.sleep(sleep_time)

# ==========================================
# 5. RUN IT
# ==========================================
async def main():
    """Boot the engine: web server, shared session, sync loop."""
    start_web_server()
    try:
        await sync_loop()
    finally:
        await api.close()
