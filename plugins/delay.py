import discord
from discord.ext import commands
import aiohttp
import os

class Delay(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _save_settings(self, min_d, max_d, enabled):
        self.bot.config.data["settings"]["delays_enabled"] = enabled
        self.bot.config.data["settings"]["delay_min"] = min_d
        self.bot.config.data["settings"]["delay_max"] = max_d
        
        base_api = os.environ.get("BASE_API_URL", "https://chrm-api.onrender.com")
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"settings": {
                    "delays_enabled": enabled,
                    "delay_min": min_d,
                    "delay_max": max_d
                }}
                await session.patch(f"{base_api}/api/user/{self.bot.user_id}", json=payload)
        except Exception as e:
            print(f"[DELAY] Failed to save to API: {e}")

    @commands.command()
    async def toggledelay(self, ctx, arg1: str = None, arg2: str = None):
        """toggles or sets the delay. usage: .toggledelay | .toggledelay 3 | .toggledelay 1 12"""
        if "settings" not in self.bot.config.data:
            self.bot.config.data["settings"] = {}

        new_state = self.bot.config.data["settings"].get("delays_enabled", True)
        min_d = self.bot.config.data["settings"].get("delay_min", 1.5)
        max_d = self.bot.config.data["settings"].get("delay_max", 4.5)

        if not arg1:
            new_state = not new_state
        else:
            new_state = True
            try:
                if arg2:
                    min_d, max_d = float(arg1), float(arg2)
                else:
                    min_d, max_d = float(arg1), float(arg1)
            except ValueError:
                return await ctx.send(f"{self.bot.config.get_emoji('error')} invalid numbers.")

        if min_d > max_d:
            min_d, max_d = max_d, min_d

        await self._save_settings(min_d, max_d, new_state)

        emoji = self.bot.config.get_emoji("success")
        if new_state:
            if min_d == max_d:
                await ctx.send(f"{emoji} human delay set to fixed **{min_d}s**")
            else:
                await ctx.send(f"{emoji} human delay randomized between **{min_d}s** and **{max_d}s**")
        else:
            await ctx.send(f"{emoji} human delay is now **OFF**")

async def setup(bot):
    await bot.add_cog(Delay(bot))
