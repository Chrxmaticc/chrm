import os
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import discord
from discord.ext import commands

# ==========================================
# 1. MINIMAL WEB SERVER (Fix 405 Error)
# ==========================================
class SimpleHandler(BaseHTTPRequestHandler):
    # Render and UptimeRobot use GET and HEAD
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"chrm is online")

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()

    def log_message(self, format, *args):
        pass # Silence the logs so it doesn't spam your console

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    print(f"🌐 Web server running on port {port}")
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()

# ==========================================
# 2. THE REGULAR BOT
# ==========================================
class ConfigManager:
    def __init__(self, user_data):
        with open("config.json", "r") as f:
            self.data = json.load(f)
        
        # Merge user data safely
        if user_data:
            self.data.update(user_data)

        # BULLETPROOFING: Ensure all features exist
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

    async def setup_hook(self):
        if os.path.exists('./plugins'):
            for filename in os.listdir('./plugins'):
                if filename.endswith('.py') and not filename.startswith('__'):
                    try:
                        await self.load_extension(f'plugins.{filename[:-3]}')
                        print(f"[+] loaded plugin: {filename}")
                    except Exception as e:
                        print(f"[-] failed to load {filename}: {e}")

    async def on_ready(self):
        print(f"✅ logged in as {self.user.name}")

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        error_emoji = self.config.get_emoji("error")
        await ctx.send(f"{error_emoji} error: {str(error).lower()}")

# ==========================================
# 3. RUN IT
# ==========================================
if __name__ == "__main__":
    token = os.environ.get("TEST_TOKEN")
    if not token:
        print("❌ CRITICAL: 'TEST_TOKEN' environment variable is missing!")
    else:
        print("🤖 starting chrm selfbot engine...")
        bot = ChrmInstance("test_user", token, {})
        bot.run(token)
