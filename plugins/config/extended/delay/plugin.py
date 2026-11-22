import discord
from discord.ext import commands

from core import api

class DelayMixin:
    """Commands for this sub-cog; assembled into the package cog."""
    async def _save_settings(self, min_d, max_d, enabled):
        await api.save_settings(self.bot, delays_enabled=enabled, delay_min=min_d, delay_max=max_d)

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
