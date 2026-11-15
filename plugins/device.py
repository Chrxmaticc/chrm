import discord
from discord.ext import commands
import aiohttp
import os

class Device(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Use the base API URL
        self.base_api = os.environ.get("BASE_API_URL", "https://chrm-api.onrender.com")

    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def device(self, ctx, platform: str):
        """changes your device client. usage: .device ios / android / windows / xbox"""
        platform = platform.lower()
        
        # Valid platforms supported by discord.py-self
        valid = ["windows", "macos", "linux", "ios", "android", "xbox", "playstation", "vr"]
        
        if platform not in valid:
            error = self.bot.config.get_emoji("error")
            return await ctx.send(f"{error} invalid platform. choose from: `{', '.join(valid)}`")

        success = self.bot.config.get_emoji("success")
        loading = self.bot.config.get_emoji("loading")
        
        await ctx.send(f"{loading} switching device to **{platform}** and reconnecting...")

        # 1. Update the database so it remembers the setting
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_api}/api/user/{self.bot.user_id}"
                payload = {"settings": {"device_platform": platform}}
                async with session.patch(url, json=payload) as resp:
                    if resp.status != 200:
                        print(f"Failed to save device to DB: {resp.status}")
        except Exception as e:
            print(f"API error: {e}")

        # 2. Disconnect the bot so main.py's sync loop reboots it with the new platform
        await ctx.send(f"{success} applying spoof. engine will be back online in ~30 seconds.")
        await self.bot.close()

async def setup(bot):
    await bot.add_cog(Device(bot))
