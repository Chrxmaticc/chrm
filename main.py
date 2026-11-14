import os
import json
import asyncio
import random
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import aiohttp
import discord
from discord.ext import commands

# ==========================================
# 1. WEB SERVER FOR RENDER (Runs instantly)
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
        pass # Silence logs

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    print(f"🌐 Web server running on port {port}")
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# ==========================================
# 2. MULTI-USER ENGINE SETUP
# ==========================================
# These MUST be set in Render's environment variables
API_URL = os.environ.get("API_URL") # e.g., https://chrm-api.onrender.com/api/engine/bots
ENGINE_SECRET = os.environ.get("ENGINE_SECRET")

class ConfigManager:
    def __init__(self, user_data):
        # Load default config template
        with open("config.json", "r") as f:
            self.data = json.load(f)
            
        # Merge user specific settings from DB
        if user_data:
            self.data.update(user_data)
            
        # Bulletproofing: Ensure dictionaries exist to prevent crashes
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

class ChrmInstance(commands.Bot):
    def __init__(self, user_id, token, user_config_data):
        super().__init__(command_prefix=".", self_bot=True, help_command=None)
        self.user_id = user_id
        self.token = token
        self.config = ConfigManager(user_config_data)
        self.locked_presence = False

    async def setup_hook(self):
        # Load all plugins
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
        error_emoji = self.config.get_emoji("error")
        await ctx.send(f"{error_emoji} error: {str(error).lower()}")

# ==========================================
# 3. FETCH & START BOTS
# ==========================================
async def fetch_users_from_api():
    """Fetches tokens from the API securely using the ENGINE_SECRET."""
    if not API_URL or not ENGINE_SECRET:
        print("❌ API_URL or ENGINE_SECRET environment variables are missing!")
        return []
        
    headers = {"x-engine-secret": ENGINE_SECRET}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status == 401:
                    print("❌ API rejected us! The ENGINE_SECRET is wrong.")
                    return []
                else:
                    print(f"❌ API returned status {resp.status}")
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
        user_config_data=user_data.get("settings", {})
    )
    
    try:
        await bot.start(token)
    except discord.LoginFailure:
        print(f"❌ Login failed for {user_data['discord_id']}: Invalid token")
    except Exception as e:
        print(f"❌ Bot crashed for {user_data['discord_id']}: {e}")
        traceback.print_exc()

# ==========================================
# 4. RUN IT
# ==========================================
async def main():
    print("🤖 fetching users from API...")
    users = await fetch_users_from_api()
    
    if not users:
        print("⚠️ No users found in database. Waiting for users...")
        # Keep the web server alive even if no users are in the DB
        while True:
            await asyncio.sleep(3600)
    else:
        print(f"Found {len(users)} users. Starting engines...")
        # Create a task for each user's bot
        tasks = [start_bot_for_user(u) for u in users]
        # Run all bots concurrently
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
