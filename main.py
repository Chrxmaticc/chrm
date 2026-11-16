import os
import json
import asyncio
import traceback
import random
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import aiohttp
import discord
from discord.ext import commands
from datetime import datetime

# ==========================================
# 1. WEB SERVER FOR RENDER (Starts instantly)
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
    print(f"🌐 Web server running on port {port}")
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
# 3. MULTI-USER BOT INSTANCE (VR PATCH)
# ==========================================
class ChrmInstance(commands.Bot):
    def __init__(self, user_id, token, user_config_data):
        prefixes = user_config_data.get("settings", {}).get("prefixes", [".", ",", "?"])
        if "." not in prefixes:
            prefixes.append(".")
            
        raw_platform = user_config_data.get("settings", {}).get("device_platform", "windows").lower()
        
        base_platform = "android" if raw_platform in ["oculus", "vr"] else raw_platform
        valid_platforms = ["windows", "macos", "linux", "ios", "android", "xbox", "playstation"]
        
        if base_platform not in valid_platforms:
            base_platform = "windows"
            
        super().__init__(command_prefix=prefixes, self_bot=True, help_command=None, platform=base_platform)
        
        self.user_id = user_id
        self.token = token
        self.config = ConfigManager(user_config_data)
        self.locked_presence = False
        self.actual_platform = raw_platform

    async def before_identify_hook(self, shard_id, *, initial=False):
        try:
            await super().before_identify_hook(shard_id, initial=initial)
        except Exception:
            pass
            
        if self.actual_platform in ["oculus", "vr"] and hasattr(self, 'ws') and self.ws:
            try:
                self.ws._connection.properties = {
                    "$os": "android",
                    "$browser": "Discord Android",
                    "$device": "Oculus Quest",
                    "$system_locale": "en-US",
                    "$timezone": "America/New_York",
                    "client_version": "201.0",
                    "release_channel": "googleRelease",
                    "os_version": "12",
                    "device_vendor_id": "Oculus",
                    "device_model": "Quest 2",
                    "browser_user_agent": "Discord-Android/201000",
                    "browser_version": "201.0",
                    "os_sdk_version": "31"
                }
                print(f"[VR] Patched properties for {self.user_id}")
            except Exception as e:
                print(f"[-] Failed to patch VR properties for {self.user_id}: {e}")

    async def human_delay(self):
        settings = self.config.data.get("settings", {})
        if settings.get("delays_enabled", True):
            min_d = settings.get("delay_min", 1.5)
            max_d = settings.get("delay_max", 4.5)
            await asyncio.sleep(random.uniform(min_d, max_d))

    async def invoke(self, ctx):
        await self.human_delay()
        await super().invoke(ctx)

    async def setup_hook(self):
        if os.path.exists('./plugins'):
            for filename in os.listdir('./plugins'):
                if filename.endswith('.py') and not filename.startswith('__'):
                    try:
                        await self.load_extension(f'plugins.{filename[:-3]}')
                    except Exception as e:
                        print(f"[-] failed to load {filename}: {e}")

    async def on_ready(self):
        print(f"✅ logged in as {self.user.name} (id: {self.user_id}) [{self.ws.platform}]")
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
                print(f"❌ Failed to apply RPC for {self.user_id}: {e}")

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

running_bots = {}

async def fetch_users_from_api():
    if not API_URL or not ENGINE_SECRET:
        return []
        
    headers = {"x-engine-secret": ENGINE_SECRET}
    timeout = aiohttp.ClientTimeout(total=5) # 5 second timeout to prevent hanging
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(API_URL, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None # Return None to signal an error, not an empty list
    except Exception:
        return None

async def start_bot_for_user(user_data):
    token = user_data.get("token")
    uid = user_data["discord_id"]
    
    if not token:
        return

    bot = ChrmInstance(uid, token, user_data)
    running_bots[uid] = bot

    try:
        print(f"⏳ Attempting login for {uid}...")
        await bot.start(token)
    except discord.LoginFailure:
        print(f"❌ Invalid token for {uid}. Deleting from memory.")
    except Exception as e:
        print(f"❌ Bot crashed for {uid}: {e}")
    finally:
        if uid in running_bots:
            del running_bots[uid]
            print(f"🧹 Cleaned up dead instance for {uid}")

async def sync_loop():
    print("🤖 starting 1-second sync loop...")
    api_errors = 0
    
    while True:
        # Start a timer to ensure we run exactly every 1 second
        start_time = time.time()
        
        users = await fetch_users_from_api()
        
        # If API fails, wait 5 seconds to prevent spamming
        if users is None:
            api_errors += 1
            if api_errors % 10 == 1: # Only log every 10 errors to prevent spam
                print("⚠️ API connection failed or timed out. Backing off...")
            await asyncio.sleep(5)
            continue
        
        api_errors = 0 # Reset errors on success

        if users:
            # Detect bots that died silently
            for uid in list(running_bots.keys()):
                if running_bots[uid].is_closed():
                    del running_bots[uid]
                    print(f"🧹 Detected closed instance for {uid}. Removed.")

            for user in users:
                uid = user["discord_id"]
                is_active = user["is_active"]
                settings = user["settings"]

                if not is_active and uid in running_bots:
                    print(f"🛑 stopping bot for {uid}")
                    await running_bots[uid].close()
                    continue

                if is_active and uid not in running_bots:
                    print(f"🚀 instantly starting bot for {uid}...")
                    asyncio.create_task(start_bot_for_user(user))
                    continue

                if is_active and uid in running_bots:
                    bot = running_bots[uid]
                    if bot.config.data != user:
                        print(f"🔄 updated settings for {uid}")
                        bot.config.data.update(user)
                        
                        new_prefixes = user.get("settings", {}).get("prefixes", [".", ",", "?"])
                        if "." not in new_prefixes:
                            new_prefixes.append(".")
                        bot.command_prefix = new_prefixes
                        await bot.apply_dashboard_rpc(user.get("settings", {}))

        # Calculate how long the loop took to run
        elapsed = time.time() - start_time
        # Sleep for the remainder of the 1 second
        sleep_time = max(0, 1.0 - elapsed)
        await asyncio.sleep(sleep_time)

# ==========================================
# 5. RUN IT
# ==========================================
async def main():
    await sync_loop()

if __name__ == "__main__":
    asyncio.run(main())
