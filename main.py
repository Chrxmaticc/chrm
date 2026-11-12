import os
import json
import asyncio
import random
from dotenv import load_dotenv
import discord
from discord.ext import commands

from security import decrypt_token

load_dotenv()

# --- config manager ---
class ConfigManager:
    def __init__(self, data):
        # we copy the default config and update it with user specific data
        with open("config.json", "r") as f:
            self.data = json.load(f)
        self.data.update(data)

    def get_emoji(self, name):
        return self.data["emojis"].get(name, "")

    def get_feature(self, name):
        return self.data["features"].get(name)


# --- multi-user bot class ---
class ChrmInstance(commands.Bot):
    def __init__(self, user_id, token, user_config_data):
        super().__init__(command_prefix=".", self_bot=True, help_command=None)
        self.user_id = user_id
        self.token = token
        self.config = ConfigManager(user_config_data)

    async def human_delay(self):
        settings = self.config.data["settings"]
        if settings.get("delays_enabled", True):
            min_d = settings.get("delay_min", 1.5)
            max_d = settings.get("delay_max", 4.5)
            await asyncio.sleep(random.uniform(min_d, max_d))

    async def setup_hook(self):
        # load plugins
        for filename in os.listdir('./plugins'):
            if filename.endswith('.py') and not filename.startswith('__'):
                try:
                    await self.load_extension(f'plugins.{filename[:-3]}')
                except Exception as e:
                    print(f"[-] failed to load {filename} for {self.user_id}: {e}")

    async def on_ready(self):
        print(f"logged in as {self.user.name} (user id: {self.user_id})")

    async def on_command_error(self, ctx, error):
        error_emoji = self.config.get_emoji("error")
        if isinstance(error, commands.CommandNotFound):
            return
        await ctx.send(f"{error_emoji} error: {str(error).lower()}")


# --- mock database (replace this with neon db fetch later) ---
MOCK_USERS = [
    {
        "discord_id": "123456789",
        # in production, this is your encrypted token string
        # for local testing right now, put your plain token in .env as TEST_TOKEN
        "encrypted_token": "mock_encrypted_token_here", 
        "settings": {
            "features": {
                "afk": {"enabled": False, "message": "afk"}
            }
        }
    }
]


async def start_bot_for_user(user_data):
    # 1. decrypt token
    # if testing locally, we bypass decryption if the token starts with "mock_"
    if user_data["encrypted_token"].startswith("mock_"):
        token = os.environ.get("TEST_TOKEN") 
    else:
        token = decrypt_token(user_data["encrypted_token"])

    if not token:
        print(f"no token found for {user_data['discord_id']}")
        return

    # 2. spin up instance
    bot = ChrmInstance(
        user_id=user_data["discord_id"], 
        token=token, 
        user_config_data=user_data["settings"]
    )
    
    # 3. start it
    try:
        await bot.start(token)
    except Exception as e:
        print(f"bot {user_data['discord_id']} crashed: {e}")


async def main():
    tasks = []
    # 1. fetch all users from db (mocked here)
    for user in MOCK_USERS:
        tasks.append(start_bot_for_user(user))
    
    # 2. run all bots concurrently
    print("starting chrm worker engine...")
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
