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
# 1. WEB SERVER FOR RENDER
# ==========================================
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"online")
    def do_HEAD(self):
        self.send_response(200)
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
# 2. ENGINE SETUP
# ==========================================
API_URL = os.environ.get("API_URL")
ENGINE_SECRET = os.environ.get("ENGINE_SECRET")

# Tracks running bots { discord_id: bot_instance }
running_bots = {}

class ConfigManager:
    def __init__(self, user_data):
        with open("config.json", "r") as f:
            self.data = json.load(f)
        if user_data:
            self.data.update(user_data)

    def get_emoji(self, name):
        return self.data.get("emojis", {}).get(name, "")

class ChrmInstance(commands.Bot):
    def __init__(self, user_id, token, user_config_data):
        super().__init__(command_prefix=".", self_bot=True, help_command=None)
        self.user_id = user_id
        self.token = token
        self.config = ConfigManager(user_config_data)

    async def setup_hook(self):
        if os.path.exists('./plugins'):
            for filename in os.listdir('./plugins'):
                if filename.endswith('.py') and not filename.startswith('__'):
                    try:
                        await self.load_extension(f'plugins.{filename[:-3]}')
                    except Exception as e:
                        print(f"[-] failed to load {filename}: {e}")

    async def on_ready(self):
        print(f"✅ logged in as {self.user.name} (id: {self.user_id})")

# ==========================================
# 3. SYNC LOOP (The Dashboard Magic)
# ==========================================
async def sync_loop():
    """Runs every 30 seconds to check dashboard changes."""
    while True:
        headers = {"x-engine-secret": ENGINE_SECRET}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(API_URL, headers=headers) as resp:
                    if resp.status != 200:
                        await asyncio.sleep(30)
                        continue
                    
                    users = await resp.json()
                    
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
                            print(f"🚀 starting bot for {uid} (dashboard toggle)")
                            bot = ChrmInstance(uid, user["token"], settings)
                            running_bots[uid] = bot
                            asyncio.create_task(bot.start(user["token"]))
                            continue

                        # 3. User is active, but changed settings (e.g., prefix, autorespond)
                        if is_active and uid in running_bots:
                            bot = running_bots[uid]
                            if bot.config.data != settings:
                                print(f"🔄 updated settings for {uid}")
                                # Update config in memory
                                bot.config.data.update(settings)
                                # If prefix changed, update the bot object
                                if "settings" in settings and "prefix" in settings["settings"]:
                                    bot.command_prefix = settings["settings"]["prefix"]

        except Exception as e:
            print(f"Sync loop error: {e}")
            
        await asyncio.sleep(30)

# ==========================================
# 4. RUN IT
# ==========================================
async def main():
    print("🤖 starting sync loop...")
    await sync_loop()

if __name__ == "__main__":
    asyncio.run(main())
