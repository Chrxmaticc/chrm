import os
import json
import asyncio
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import aiohttp
import discord
from discord.ext import commands

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
        pass # Silence logs to prevent spam

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
            
        # Merge user specific settings
        if user_data:
            self.data.update(user_data)
            
        # Bulletproofing: Ensure dictionaries exist to prevent crashes
        if "settings" not in self.data:
            self.data["settings"] = {}
        if "features" not in self.data:
            self.data["features"] = {}
        if "autorespond" not in self.data["features"]:
            self.data["features"]["autorespond"] = {}
        if "autoreact" not in self.data["features"]:
            self.data["features"]["autoreact"] = {}
        if "afk" not in self.data["features"]:
            self.data["features"]["afk"] = {"enabled": False, "message": "afk"}
        if "status_rotator" not in self.data["features"]:
            self.data["features"]["status_rotator"] = {
                "enabled": True,
                "statuses": ["chrm on top", "vibing", "afk", "learning python"]
            }

    def get_emoji(self, name):
        return self.data.get("emojis", {}).get(name, "")

# ==========================================
# 3. MULTI-USER BOT INSTANCE
# ==========================================
class ChrmInstance(commands.Bot):
    def __init__(self, user_id, token, user_config_data):
        # Handle Multiple Prefixes with Emergency Fallback
        prefixes = user_config_data.get("settings", {}).get("prefixes", [".", ",", "?"])
        if "." not in prefixes:
            prefixes.append(".") # Emergency fallback so they can always reset
            
        super().__init__(command_prefix=prefixes, self_bot=True, help_command=None)
        
        self.user_id = user_id
        self.token = token
        self.config = ConfigManager(user_config_data)
        self.locked_presence = False

    async def human_delay(self):
        settings = self.config.data.get("settings", {})
        if settings.get("delays_enabled", True):
            min_d = settings.get("delay_min", 1.5)
            max_d = settings.get("delay_max", 4.5)
            await asyncio.sleep(random.uniform(min_d, max_d))

    async def setup_hook(self):
        # Load plugins
        if os.path.exists('./plugins'):
            for filename in os.listdir('./plugins'):
                if filename.endswith('.py') and not filename.startswith('__'):
                    try:
                        await self.load_extension(f'plugins.{filename[:-3]}')
                        print(f"[+] loaded {filename} for {self.user_id}")
                    except Exception as e:
                        print(f"[-] failed to load {filename}: {e}")

    async def on_ready(self):
        print(f"✅ logged in as {self.user.name} (id: {self.user_id})")

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
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

# Tracks running bots { discord_id: bot_instance }
running_bots = {}

async def fetch_users_from_api():
    if not API_URL or not ENGINE_SECRET:
        print("❌ CRITICAL: API_URL or ENGINE_SECRET is missing in Render Env Vars!")
        return []
        
    headers = {"x-engine-secret": ENGINE_SECRET}
    timeout = aiohttp.ClientTimeout(total=60)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(API_URL, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status == 401:
                    print("❌ Unauthorized! ENGINE_SECRET in Backend does not match API.")
                    return []
                else:
                    print(f"⚠️ API returned status {resp.status}")
                    return []
    except asyncio.TimeoutError:
        print("⏳ API took too long to respond. Is Render asleep?")
        return []
    except Exception as e:
        print(f"❌ Failed to connect to API: {e}")
        return []

async def start_bot_for_user(user_data):
    token = user_data.get("token")
    if not token:
        return

    bot = ChrmInstance(
        user_id=user_data["discord_id"], 
        token=token, 
        user_config_data=user_data
    )
    
    try:
        await bot.start(token)
    except discord.LoginFailure:
        print(f"❌ Improper token for {user_data['discord_id']}. Skipping...")
    except Exception as e:
        print(f"❌ Bot crashed for {user_data['discord_id']}: {e}")

async def sync_loop():
    """Runs every 30 seconds to check dashboard changes."""
    print("🤖 starting sync loop...")
    
    while True:
        users = await fetch_users_from_api()
        
        if not users:
            await asyncio.sleep(30)
            continue

        print(f"👥 Found {len(users)} users in database.")
        
        for user in users:
            uid = user["discord_id"]
            is_active = user["is_active"]
            settings = user["settings"]

            # 1. User turned bot OFF from dashboard
            if not is_active and uid in running_bots:
                print(f"🛑 stopping bot for {uid} (dashboard toggle)")
                await running_bots[uid].close()
                del running_bots[uid]
                continue

            # 2. User turned bot ON from dashboard
            if is_active and uid not in running_bots:
                print(f"🚀 starting bot for {uid}...")
                bot = ChrmInstance(uid, user["token"], user)
                running_bots[uid] = bot
                asyncio.create_task(start_bot_for_user(user))
                continue

            # 3. User is active, but changed settings (e.g., prefix, autorespond)
            if is_active and uid in running_bots:
                bot = running_bots[uid]
                if bot.config.data != user:
                    print(f"🔄 updated settings for {uid}")
                    bot.config.data.update(user)
                    
                    # If prefixes changed, update them live
                    new_prefixes = user.get("settings", {}).get("prefixes", [".", ",", "?"])
                    if "." not in new_prefixes:
                        new_prefixes.append(".")
                    bot.command_prefix = new_prefixes

        await asyncio.sleep(30)

# ==========================================
# 5. RUN IT
# ==========================================
async def main():
    await sync_loop()

if __name__ == "__main__":
    import random # imported here for the human_delay method
    asyncio.run(main())
