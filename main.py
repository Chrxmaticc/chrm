import os
import json
import asyncio
import random
import time
import traceback
import gc
import psutil
from dotenv import load_dotenv
from api_base import BASE_API
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import aiohttp
import discord
from discord.ext import commands
from datetime import datetime

# Load .env before anything reads os.environ (PORT, API_URL, ENGINE_SECRET).
load_dotenv()

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

threading.Thread(target=run_web_server, daemon=True).start()

# ==========================================
# 2. CONFIG MANAGER
# ==========================================
class ConfigManager:
    def __init__(self, user_data):
        with open("config.json", "r") as f:
            self.data = json.load(f)
            
        if user_data:
            self.data.update(user_data)
            
        if "settings" not in self.data:
            self.data["settings"] = {}
        if "prefixes" not in self.data["settings"]:
            self.data["settings"]["prefixes"] = [".", ",", "?"]
        if "features" not in self.data:
            self.data["features"] = {}
        if "autorespond" not in self.data["features"]:
            self.data["features"]["autorespond"] = {}
        if "autoreact" not in self.data["features"]:
            self.data["features"]["autoreact"] = {}
        if "afk" not in self.data["features"]:
            self.data["features"]["afk"] = {"enabled": False, "message": "afk"}

    def get_emoji(self, name):
        return self.data.get("emojis", {}).get(name, "")

# ==========================================
# 3. MULTI-USER BOT INSTANCE
# ==========================================
class ChrmInstance(commands.Bot):
    def __init__(self, user_id, token, user_config_data):
        prefixes = user_config_data.get("settings", {}).get("prefixes", [".", ",", "?"])
        if "." not in prefixes:
            prefixes.append(".")
            
        super().__init__(command_prefix=prefixes, self_bot=True, help_command=None)
        
        self.user_id = user_id
        self.token = token
        self.config = ConfigManager(user_config_data)
        self.locked_presence = False
        
        # 🚨 CRITICAL: Registers the core command so it actually works
        self.add_command(self.toggledelay)

    async def human_delay(self):
        settings = self.config.data.get("settings", {})
        if settings.get("delays_enabled", True):
            min_d = settings.get("delay_min", 1.5)
            max_d = settings.get("delay_max", 4.5)
            await asyncio.sleep(random.uniform(min_d, max_d))

    async def invoke(self, ctx):
        await self.human_delay()
        await super().invoke(ctx)

    # ==========================================
    # THE TOGGLEDELAY COMMAND
    # ==========================================
    @commands.command()
    async def toggledelay(self, ctx, arg1: str = None, arg2: str = None):
        """toggles or sets the delay. usage: .toggledelay (toggle), .toggledelay 3 (fixed), .toggledelay 1 12 (random)"""
        if "settings" not in self.config.data:
            self.config.data["settings"] = {}

        new_state = self.config.data["settings"].get("delays_enabled", True)
        min_d = self.config.data["settings"].get("delay_min", 1.5)
        max_d = self.config.data["settings"].get("delay_max", 4.5)

        if not arg1:
            new_state = not new_state
        else:
            new_state = True
            try:
                if arg2:
                    min_d = float(arg1)
                    max_d = float(arg2)
                else:
                    min_d = float(arg1)
                    max_d = float(arg1)
            except ValueError:
                error = self.config.get_emoji("error")
                return await ctx.send(f"{error} invalid numbers. usage: `.toggledelay 3` or `.toggledelay 1 12`")

        if min_d > max_d:
            min_d, max_d = max_d, min_d

        self.config.data["settings"]["delays_enabled"] = new_state
        self.config.data["settings"]["delay_min"] = min_d
        self.config.data["settings"]["delay_max"] = max_d

        try:
            async with aiohttp.ClientSession() as session:
                payload = {"settings": {
                    "delays_enabled": new_state,
                    "delay_min": min_d,
                    "delay_max": max_d
                }}
                async with session.patch(f"{BASE_API}/api/user/{self.user_id}", json=payload) as resp:
                    pass
        except Exception as e:
            print(f"Failed to save delay settings to API: {e}")

        emoji = self.config.get_emoji("success")
        if new_state:
            if min_d == max_d:
                await ctx.send(f"{emoji} human delay set to fixed **{min_d}s**")
            else:
                await ctx.send(f"{emoji} human delay randomized between **{min_d}s** and **{max_d}s**")
        else:
            await ctx.send(f"{emoji} human delay is now **OFF**")

    async def setup_hook(self):
        if os.path.exists('./plugins'):
            for filename in os.listdir('./plugins'):
                if filename.endswith('.py') and not filename.startswith('__'):
                    try:
                        await self.load_extension(f'plugins.{filename[:-3]}')
                    except Exception as e:
                        print(f"[PLUGIN ERROR] Failed to load {filename}: {e}")

    async def on_ready(self):
        print(f"✅ [ONLINE] logged in as {self.user.name} (id: {self.user_id})")
        await self.apply_dashboard_rpc(self.config.data.get("settings", {}))

    async def apply_dashboard_rpc(self, settings):
        rpc_data = settings.get("rpc")
        if rpc_data and rpc_data.get("name"):
            try:
                types = {
                    "playing": discord.ActivityType.playing,
                    "watching": discord.ActivityType.watching,
                    "listening": discord.ActivityType.listening,
                    "competing": discord.ActivityType.competing
                }
                assets = {}
                if rpc_data.get("image_url"):
                    assets["large_image"] = rpc_data["image_url"]
                    if rpc_data.get("details"):
                        assets["large_text"] = rpc_data["details"]

                timestamps = None
                if rpc_data.get("elapsed"):
                    timestamps = {"start": int(datetime.now().timestamp())}

                self.locked_presence = True
                await self.change_presence(activity=discord.Activity(
                    type=types.get(rpc_data["type"], discord.ActivityType.playing),
                    name=rpc_data["name"],
                    details=rpc_data.get("details"),
                    state=rpc_data.get("state"),
                    assets=assets if assets else None,
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
global_http_session = None 
_auth_warned_at = {}

async def fetch_users_from_api():
    if not BOTS_URL or not ENGINE_SECRET or not global_http_session:
        return None
        
    headers = {"x-engine-secret": ENGINE_SECRET}
    
    try:
        async with global_http_session.get(BOTS_URL, headers=headers) as resp:
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
        
        process = psutil.Process(os.getpid())
        ram_usage = process.memory_info().rss / 1024 / 1024
        
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
                if bot.config.data != user:
                    bot.config.data.update(user)
                    
                    new_prefixes = user.get("settings", {}).get("prefixes", [".", ",", "?"])
                    if "." not in new_prefixes:
                        new_prefixes.append(".")
                    bot.command_prefix = new_prefixes
                    await bot.apply_dashboard_rpc(user.get("settings", {}))

        elapsed = time.time() - start_time
        sleep_time = max(0, 3.0 - elapsed)
        await asyncio.sleep(sleep_time)

# ==========================================
# 5. RUN IT
# ==========================================
async def main():
    global global_http_session
    global_http_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
    
    try:
        await sync_loop()
    finally:
        await global_http_session.close()

if __name__ == "__main__":
    asyncio.run(main())
