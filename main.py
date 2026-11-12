import os
import json
import asyncio
import random
import traceback
import uvicorn
from fastapi import FastAPI
from dotenv import load_dotenv
import discord
from discord.ext import commands

load_dotenv()

# ==========================================
# 1. WEB SERVER (Starts instantly for Render)
# ==========================================
app = FastAPI()
bot_instance = None 

@app.get("/")
def read_root():
    return {"status": "chrm is running"}

@app.get("/health")
def health_check():
    is_ready = bot_instance.is_ready() if bot_instance else False
    return {"status": "online", "bot_ready": is_ready}

# ==========================================
# 2. CONFIG MANAGER
# ==========================================
class ConfigManager:
    def __init__(self, user_data):
        with open("config.json", "r") as f:
            self.data = json.load(f)
        self.data.update(user_data)

    def get_emoji(self, name):
        return self.data.get("emojis", {}).get(name, "")

    def get_feature(self, name):
        return self.data.get("features", {}).get(name)

# ==========================================
# 3. SELF-BOT ENGINE
# ==========================================
class ChrmInstance(commands.Bot):
    def __init__(self, user_id, token, user_config_data):
        super().__init__(command_prefix=".", self_bot=True, help_command=None)
        self.user_id = user_id
        self.token = token
        self.config = ConfigManager(user_config_data)

    async def human_delay(self):
        settings = self.config.data.get("settings", {})
        if settings.get("delays_enabled", True):
            min_d = settings.get("delay_min", 1.5)
            max_d = settings.get("delay_max", 4.5)
            await asyncio.sleep(random.uniform(min_d, max_d))

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
        print(f"✅ logged in as {self.user.name} (id: {self.user_id})")

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        error_emoji = self.config.get_emoji("error")
        await ctx.send(f"{error_emoji} error: {str(error).lower()}")

# ==========================================
# 4. MAIN EXECUTION
# ==========================================
async def start_bot():
    global bot_instance
    token = os.environ.get("TEST_TOKEN")
    
    if not token:
        print("❌ CRITICAL: 'TEST_TOKEN' environment variable is missing!")
        return

    try:
        bot_instance = ChrmInstance("test_user", token, {})
        await bot_instance.start(token)
    except discord.LoginFailure:
        print("❌ CRITICAL: The Discord token is invalid or expired.")
    except Exception:
        print("❌ CRITICAL: The bot crashed.")
        traceback.print_exc()

async def main():
    # 1. START WEB SERVER FIRST
    port = int(os.environ.get("PORT", 8080))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    
    print(f"🌐 starting web server on port {port}...")
    # Start the server as a background task
    server_task = asyncio.create_task(server.serve())
    
    # Give render 3 seconds to see the port so it doesn't kill us
    await asyncio.sleep(3)
    
    # 2. START BOT
    print("🤖 starting chrm selfbot engine...")
    bot_task = asyncio.create_task(start_bot())
    
    # Keep both running forever
    await asyncio.gather(server_task, bot_task)

if __name__ == "__main__":
    asyncio.run(main())
